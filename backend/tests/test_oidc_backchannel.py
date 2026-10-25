"""Private fixture files and mocked Docker only; no real network or host edits."""
import ipaddress
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import configure_oidc_backchannel as route

ADDRESS = str(ipaddress.IPv4Address((10 << 24) + 42))
OTHER = str(ipaddress.IPv4Address((10 << 24) + 43))


class OidcBackchannelTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="itam-oidc-route-test-")
        self.root = Path(self.temporary.name)
        self.probe = Mock()
        self.override = self.root / route.OVERRIDE

    def tearDown(self):
        self.temporary.cleanup()

    def test_empty_candidate_is_noop_even_with_unrecognized_override(self):
        original = b"services:\n  unrelated:\n    image: preserved\n"
        self.override.write_bytes(original)
        self.assertIsNone(route.read_candidate(self.root, {}))
        self.assertEqual(route.check(self.root, None, self.probe), "no_candidate_unchanged")
        self.assertEqual(route.apply(self.root, None, None, self.probe), "no_candidate_unchanged")
        self.assertEqual(self.override.read_bytes(), original)
        self.probe.assert_not_called()
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), [route.OVERRIDE])

    def test_candidate_comes_only_from_private_environment_or_server_env(self):
        self.assertEqual(route.read_candidate(self.root, {"ITAM_SSO_CANDIDATE_IP": ADDRESS}), ADDRESS)
        (self.root / ".env").write_text("OTHER_SETTING=keep\nAUTHENTIK_BACKCHANNEL_IP='" + ADDRESS + "'\n")
        original = (self.root / ".env").read_bytes()
        self.assertEqual(route.read_candidate(self.root, {}), ADDRESS)
        self.assertEqual(route.read_candidate(self.root, {"ITAM_SSO_CANDIDATE_IP": OTHER}), OTHER)
        self.assertEqual((self.root / ".env").read_bytes(), original)
        for invalid in ("127.0.0.1", "0.0.0.0", "169.254.1.2", "203.0.113.1", "::1", "candidate.invalid"):
            with self.subTest(invalid=invalid), self.assertRaises(route.Rejected) as error:
                route.read_candidate(self.root, {"ITAM_SSO_CANDIDATE_IP": invalid})
            self.assertEqual(error.exception.code, "candidate_must_be_private_ipv4")

    def test_unknown_override_is_preserved_without_probe_or_apply(self):
        original = b'{"services":{"backend":{"environment":{"KEEP":"unchanged"}}}}'
        self.override.write_bytes(original)
        for operation in (lambda: route.check(self.root, ADDRESS, self.probe),
                          lambda: route.apply(self.root, ADDRESS, "100", self.probe)):
            with self.assertRaises(route.Rejected) as error:
                operation()
            self.assertEqual(error.exception.code, "unrecognized_compose_override_preserved")
            self.assertEqual(self.override.read_bytes(), original)
        self.probe.assert_not_called()
        self.assertFalse((self.root / route.ACTIVE).exists())

    def test_certificate_failure_never_writes_an_override_or_active_marker(self):
        self.probe.side_effect = route.Rejected("tls_certificate_error")
        with self.assertRaises(route.Rejected) as error:
            route.apply(self.root, ADDRESS, "101", self.probe)
        self.assertEqual(error.exception.code, "tls_certificate_error")
        self.assertFalse(self.override.exists())
        self.assertFalse((self.root / route.ACTIVE).exists())
        self.assertFalse(list((self.root / "backups").glob("oidc-backchannel-*.json")))

    def test_success_is_backend_only_private_idempotent_and_can_restore(self):
        self.assertEqual(route.apply(self.root, ADDRESS, "102", self.probe), "applied")
        expected = route.override_bytes(ADDRESS)
        self.assertEqual(self.override.read_bytes(), expected)
        value = json.loads(expected)
        self.assertEqual(set(value["services"]), {"backend"})
        self.assertEqual(set(value["services"]["backend"]), {"extra_hosts"})
        self.assertEqual(route.apply(self.root, ADDRESS, "102", self.probe), "already_applied")
        for file in (self.override, self.root / route.ACTIVE, self.root / "backups/oidc-backchannel-102.json"):
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        self.assertEqual(route.restore(self.root, "102"), "restored")
        self.assertFalse(self.override.exists())
        self.assertFalse((self.root / route.ACTIVE).exists())
        self.assertEqual(route.restore(self.root, "102"), "no_managed_change")
        self.assertEqual(route.apply(self.root, ADDRESS, "102", self.probe), "applied")

    def test_existing_managed_route_restores_exact_bytes_and_finalize_keeps_backup(self):
        previous = route.override_bytes(OTHER) + b"\n"
        self.override.write_bytes(previous)
        route.apply(self.root, ADDRESS, "103", self.probe)
        route.restore(self.root, "103")
        self.assertEqual(self.override.read_bytes(), previous)
        route.apply(self.root, ADDRESS, "104", self.probe)
        self.assertEqual(route.finalize(self.root, "104"), "finalized_backup_preserved")
        self.assertEqual(route.owned_override(self.override.read_bytes()), ADDRESS)
        self.assertFalse((self.root / route.ACTIVE).exists())
        self.assertTrue((self.root / "backups/oidc-backchannel-104.json").exists())
        self.assertEqual(route.apply(self.root, ADDRESS, "105", self.probe), "verified_existing_route_unchanged")
        self.assertFalse((self.root / route.ACTIVE).exists())

    def test_different_run_or_modified_file_cannot_be_overwritten_or_restored(self):
        route.apply(self.root, ADDRESS, "106", self.probe)
        for action in (lambda: route.restore(self.root, "107"), lambda: route.finalize(self.root, "107"),
                       lambda: route.apply(self.root, OTHER, "107", self.probe)):
            with self.assertRaises(route.Rejected):
                action()
        self.assertEqual(route.owned_override(self.override.read_bytes()), ADDRESS)
        changed = b'{"services":{"custom":{"image":"keep"}}}'
        self.override.write_bytes(changed)
        for action in (lambda: route.restore(self.root, "106"), lambda: route.finalize(self.root, "106")):
            with self.assertRaises(route.Rejected):
                action()
        self.assertEqual(self.override.read_bytes(), changed)

    def test_interrupted_apply_with_unchanged_override_can_restore_safely(self):
        original = route.private_write
        def failed(path, *args, **kwargs):
            if path == self.override:
                raise OSError("fixture write failure")
            return original(path, *args, **kwargs)
        with patch.object(route, "private_write", side_effect=failed), self.assertRaises(OSError):
            route.apply(self.root, ADDRESS, "108", self.probe)
        self.assertTrue((self.root / route.ACTIVE).exists())
        self.assertEqual(route.restore(self.root, "108"), "already_restored")
        self.assertFalse(self.override.exists())

    def test_probe_uses_existing_backend_network_stdin_candidate_and_no_credentials(self):
        runner = Mock(side_effect=[subprocess.CompletedProcess([], 0, "a" * 64 + "\n", ""),
            subprocess.CompletedProcess([], 0, '{"ok":true,"result":"tls_token_jwks_verified"}', "")])
        route.probe_candidate(self.root, ADDRESS, runner)
        command = runner.call_args_list[1].args[0]
        self.assertEqual(command[:5], ["docker", "exec", "-i", "-w", "/app"])
        self.assertNotIn(ADDRESS, " ".join(command))
        self.assertEqual(json.loads(runner.call_args_list[1].kwargs["input"]), {"candidate": ADDRESS, "verify_running": False})
        self.assertNotIn("CLIENT_SECRET", route.PROBE_SOURCE)
        self.assertNotIn("CERT_NONE", route.PROBE_SOURCE)
        self.assertNotIn("'POST'", route.PROBE_SOURCE)
        compile(route.PROBE_SOURCE, "credential_free_tls_probe", "exec")

    def test_certificate_error_and_malformed_docker_output_are_sanitized(self):
        for output, expected in ((json.dumps({"ok":False,"result":"tls_certificate_error"}), "tls_certificate_error"),
                                 (json.dumps({"ok":False,"result":"private-host-secret"}), "invalid_probe_result"),
                                 ("private traceback or token", "probe_unavailable")):
            runner = Mock(side_effect=[subprocess.CompletedProcess([], 0, "b" * 64, ""),
                subprocess.CompletedProcess([], 1, output, "private stderr")])
            with self.assertRaises(route.Rejected) as error:
                route.probe_candidate(self.root, ADDRESS, runner)
            self.assertEqual(error.exception.code, expected)

    def test_stale_private_temporary_files_cannot_block_apply_or_restore(self):
        orphan = self.root / ".itam-oidc-stale.tmp"
        old_name = self.root / (route.OVERRIDE + ".tmp")
        orphan.write_bytes(b"interrupted private write")
        old_name.write_bytes(b"old interrupted write")
        self.assertEqual(route.apply(self.root, ADDRESS, "109", self.probe), "applied")
        self.assertEqual(route.restore(self.root, "109"), "restored")
        self.assertEqual(orphan.read_bytes(), b"interrupted private write")
        self.assertEqual(old_name.read_bytes(), b"old interrupted write")
        self.assertEqual(list(self.root.glob(".itam-oidc-*.tmp")), [orphan])

    def test_backup_marker_and_override_directory_entries_are_synced_in_order(self):
        events = []
        original = route.sync_directory
        backup = self.root / "backups/oidc-backchannel-110.json"
        def recorded(path):
            original(path)
            events.append((backup.exists(), (self.root / route.ACTIVE).exists(), self.override.exists()))
        with patch.object(route, "sync_directory", side_effect=recorded):
            route.apply(self.root, ADDRESS, "110", self.probe)
        self.assertLess(events.index((True, False, False)), events.index((True, True, False)))
        self.assertLess(events.index((True, True, False)), events.index((True, True, True)))
        events.clear()
        with patch.object(route, "sync_directory", side_effect=recorded):
            route.restore(self.root, "110")
        self.assertLess(events.index((True, True, False)), events.index((True, False, False)))

    def test_maximum_size_owned_override_backup_remains_readable_and_exactly_restorable(self):
        base = route.override_bytes(OTHER)
        previous = base + b" " * (route.LIMIT - len(base))
        self.override.write_bytes(previous)
        route.apply(self.root, ADDRESS, "111", self.probe)
        backup = self.root / "backups/oidc-backchannel-111.json"
        self.assertGreater(backup.stat().st_size, route.LIMIT)
        self.assertLessEqual(backup.stat().st_size, route.STATE_LIMIT)
        self.assertEqual(route.apply(self.root, ADDRESS, "111", self.probe), "already_applied")
        self.assertEqual(route.restore(self.root, "111"), "restored")
        self.assertEqual(self.override.read_bytes(), previous)
        self.assertEqual(route.apply(self.root, ADDRESS, "111", self.probe), "applied")

    def test_oversized_serialized_state_is_rejected_before_file_creation(self):
        target = self.root / "oversized.json"
        with self.assertRaises(route.Rejected) as error:
            route.private_write(target, b"x" * (route.STATE_LIMIT + 1), limit=route.STATE_LIMIT)
        self.assertEqual(error.exception.code, "managed_state_too_large")
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".itam-oidc-*.tmp")))


if __name__ == "__main__":
    unittest.main()
