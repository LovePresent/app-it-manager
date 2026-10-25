import contextlib
import io
import json
import socket
import ssl
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import configure_oidc_backchannel as route


class RunningRouteTests(unittest.TestCase):
    def execute_probe(self, resolved):
        settings = types.SimpleNamespace(AUTHENTIK_TOKEN_URL='https://auth.cqv.kr/application/o/token/',
            AUTHENTIK_BASE_URL='https://auth.cqv.kr', AUTHENTIK_JWKS_URL='https://auth.cqv.kr/application/o/itam/jwks/')
        outputs = io.StringIO()
        statuses = iter((405, 200))
        connections = []
        def connection(host, port, timeout, context):
            self.assertEqual((host, port), ('auth.cqv.kr', 443))
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            value = Mock()
            response = Mock(status=next(statuses))
            response.read.return_value = json.dumps({'keys': [{'kty': 'RSA', 'kid': 'fixture', 'n': 'fixture', 'e': 'AQAB'}]}).encode()
            value.getresponse.return_value = response
            connections.append(value)
            return value
        with patch.dict(sys.modules, {'app.config': types.SimpleNamespace(settings=settings)}), \
             patch('sys.stdin', io.StringIO(json.dumps({'candidate':'10.250.0.5', 'verify_running':True}))), \
             patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (resolved, 443))]), \
             patch('socket.create_connection') as direct, patch('http.client.HTTPSConnection', side_effect=connection), \
             contextlib.redirect_stdout(outputs):
            try:
                exec(compile(route.PROBE_SOURCE, '<probe>', 'exec'), {})
            except SystemExit as result:
                self.assertEqual(result.code, 1)
        direct.assert_not_called()
        return json.loads(outputs.getvalue()), connections

    def test_stale_running_dns_rejects_before_any_http_request(self):
        result, connections = self.execute_probe('192.0.2.5')
        self.assertEqual(result, {'ok': False, 'result':'running_route_mismatch'})
        connections[0].request.assert_not_called()

    def test_verified_running_dns_uses_normal_hostname_https_for_both_endpoints(self):
        result, connections = self.execute_probe('10.250.0.5')
        self.assertTrue(result['ok'])
        self.assertEqual(len(connections), 2)
        for connection in connections:
            connection.request.assert_called_once()

    def test_conflicting_alternate_override_is_preserved_before_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = b'services:\n  backend:\n    environment:\n      FIXTURE: preserve\n'
            path = root / 'compose.override.yaml'
            path.write_bytes(original)
            probe = Mock()
            with self.assertRaisesRegex(route.Rejected, 'alternate_compose_override_preserved'):
                route.check(root, '10.250.0.5', probe)
            probe.assert_not_called()
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((root / route.OVERRIDE).exists())

    def test_existing_managed_route_is_verified_when_candidate_secret_is_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / route.OVERRIDE).write_bytes(route.override_bytes('10.250.0.5'))
            probe = Mock()
            self.assertEqual(route.verify_running(root, None, probe), 'running_route_verified')
            probe.assert_called_once_with(root, '10.250.0.5', normal_dns=True)


if __name__ == '__main__':
    unittest.main()
