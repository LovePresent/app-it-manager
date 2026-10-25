"""Append-only device ledger migration with bounded parents and preview binding.

No agent identities, credentials, enrollment tickets or executable commands are
accepted. Existing rows are never updated/deleted. Audit markers provide stable
source-row identity without adding a migration-specific database schema.
"""
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import MetaData, Table, select, text
from sqlalchemy.sql.sqltypes import JSON, Date, DateTime, Boolean, Integer, Float, String

FORMAT = "itam-device-ledger-v1"
MAX_BYTES = 8 * 1024 * 1024
ORDER = ("user_refs", "asset_categories", "vendors", "assets", "software_licenses", "purchases", "devices",
         "device_licenses", "computer_settings", "license_assignments", "purchase_allocations",
         "device_usage_history", "ip_change_history", "audit_logs")
PARENTS = {"asset_categories", "vendors", "assets", "software_licenses", "purchases"}
SECRET_KEYS = {"devicetoken", "enrollmenttoken", "registrationtoken", "tokenhash", "enrollmenthash", "clientnonce",
               "accesstoken", "refreshtoken", "authorization", "completionhash", "receipt", "uninstallcode", "password"}
MARKER = "device_ledger_migration"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=lambda item:
        {"$ref": [item.table, item.source_id]} if isinstance(item, Ref) else item.isoformat() if isinstance(item, (datetime, date)) else str(item))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def normalized(value):
    return str(value or "").strip().casefold()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def _scan(value, depth=0):
    if depth > 20:
        raise ValueError("Excessive nesting")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or normalized(key).replace("_", "").replace("-", "") in SECRET_KEYS:
                raise ValueError("Credentials are prohibited")
            _scan(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _scan(item, depth + 1)
    elif isinstance(value, str) and len(value) > 262144:
        raise ValueError("Field too long")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite number")


def parse_payload(raw):
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "가져오기 파일은 8MiB 이하이어야 합니다.")
    try:
        payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite number")))
        if set(payload) != {"format", "source_id", "batch_id", "exported_at", "tables", "excluded"} or payload["format"] != FORMAT:
            raise ValueError("Unknown format")
        for key in ("source_id", "batch_id"):
            if str(UUID(payload[key])) != payload[key] or UUID(payload[key]).int == 0:
                raise ValueError("Invalid identity")
        instant = datetime.fromisoformat(payload["exported_at"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("Missing timezone")
        if set(payload["tables"]) != set(ORDER) or not isinstance(payload["excluded"], dict):
            raise ValueError("Unexpected tables")
        if len(payload["excluded"]) > 20 or any(not isinstance(key, str) or len(key) > 80 or not isinstance(value, (str, int)) or isinstance(value, str) and len(value) > 256 for key, value in payload["excluded"].items()):
            raise ValueError("Invalid exclusion summary")
        if len(payload["tables"]["devices"]) > 5000:
            raise ValueError("Too many devices")
        for table, rows in payload["tables"].items():
            if not isinstance(rows, list) or len(rows) > 25000:
                raise ValueError("Too many rows")
            ids = [row.get("id") for row in rows if isinstance(row, dict)]
            if len(ids) != len(rows) or any(type(value) is not int or value < 1 for value in ids) or len(ids) != len(set(ids)):
                raise ValueError("Invalid source row identifiers")
        _scan(payload)
        return payload, hashlib.sha256(raw).hexdigest()
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise HTTPException(422, "장비 대장 파일 형식이나 참조 정보가 올바르지 않습니다. 인증 정보가 포함된 파일은 가져올 수 없습니다.") from exc


@dataclass(frozen=True)
class Ref:
    table: str
    source_id: int


def _row(row):
    return {key: value.isoformat() if isinstance(value, (datetime, date)) else value for key, value in row.items()}


def _business(row, historical=False):
    return {key: value for key, value in row.items() if key != "id" and (historical or key not in {"created_at", "updated_at"})}


class Planner:
    def __init__(self, connection, payload, payload_hash):
        self.connection, self.payload, self.payload_hash = connection, payload, payload_hash
        self.tables, self.existing, self.mapping, self.actions, self.entries, self.issues = {}, {}, {}, [], [], []
        self.counts = {name: {"create": 0, "reuse": 0, "skip": 0} for name in ORDER}
        self.manual = []
        metadata = MetaData()
        for name in ORDER:
            real = "users" if name == "user_refs" else name
            self.tables[name] = Table(real, metadata, autoload_with=connection, extend_existing=True)
            columns = ["id", "email", "name"] if name == "user_refs" else list(self.tables[name].columns.keys())
            self.existing[name] = [_row(row) for row in connection.execute(select(*[self.tables[name].c[key] for key in columns])).mappings()]
            for row in payload["tables"][name]:
                if set(row) != set(columns):
                    raise HTTPException(422, "장비 대장 열 구성이 현재 서버와 다릅니다. 파일을 다시 확인해 주세요.")
                for key, value in row.items():
                    column = self.tables[name].c[key]
                    valid = value is not None or column.nullable
                    if value is not None:
                        if isinstance(column.type, Boolean):
                            valid = type(value) in {bool, int} and value in (0, 1)
                        elif isinstance(column.type, Integer):
                            valid = type(value) is int
                        elif isinstance(column.type, Float):
                            valid = type(value) in {int, float}
                        elif isinstance(column.type, String):
                            valid = isinstance(value, str) and len(value) <= (column.type.length or 262144)
                        elif isinstance(column.type, DateTime):
                            try:
                                datetime.fromisoformat(value.replace("Z", "+00:00"))
                            except (ValueError, AttributeError, TypeError):
                                valid = False
                        elif isinstance(column.type, Date):
                            try:
                                date.fromisoformat(value)
                            except (ValueError, TypeError):
                                valid = False
                    if not valid:
                        raise HTTPException(422, "파일에 현재 자료형과 맞지 않는 값이 있습니다. 원본 값을 확인해 주세요.")
        self.source = {name: {row["id"]: row for row in rows} for name, rows in payload["tables"].items()}
        self.previous = {}
        self.receipt = None
        self.marker_rows = sorted([row for row in self.existing["audit_logs"] if row["entity_type"] == MARKER and row["action"] == "batch_import"], key=lambda row: row["id"])
        for row in self.marker_rows:
            changes = row["changes"] or {}
            if changes.get("batch_id") == payload["batch_id"]:
                if changes.get("payload_sha256") != payload_hash or changes.get("source_id") != payload["source_id"]:
                    raise HTTPException(409, "같은 가져오기 번호에 다른 파일이 사용되었습니다.")
                self.receipt = changes["receipt"]
            if changes.get("source_id") == payload["source_id"]:
                for entry in changes.get("rows", []):
                    self.previous[(entry["table"], entry["source_id"])] = entry
        self._validate_references()

    def _validate_references(self):
        links = {"assets": {"category_id": "asset_categories", "vendor_id": "vendors"},
                 "software_licenses": {"asset_id": "assets", "vendor_id": "vendors"},
                 "license_assignments": {"device_id": "devices", "license_id": "software_licenses"},
                 "purchase_allocations": {"resource_id": "devices", "purchase_id": "purchases"},
                 "device_licenses": {"device_id": "devices"}, "computer_settings": {"device_id": "devices"},
                 "device_usage_history": {"device_id": "devices"}, "ip_change_history": {"device_id": "devices"}}
        for table, fields in links.items():
            for row in self.source[table].values():
                for field, target in fields.items():
                    if row[field] is not None and row[field] not in self.source[target]:
                        raise HTTPException(422, "연결된 장비·라이선스·구매 자료가 파일에 없습니다.")
        for row in self.source["purchase_allocations"].values():
            if row["resource_type"] != "device" or row["quantity"] < 1:
                raise HTTPException(422, "장비 외 구매 배분은 이 가져오기 범위에 포함되지 않습니다.")
        # The shared legacy inventory accepts free-text device types and blank
        # serials. Preserve those exact values instead of imposing the automatic
        # Windows agent's narrower desktop/laptop registration vocabulary.
        for name, fields in {"license_assignments": ("device_id", "license_id"),
                             "purchase_allocations": ("purchase_id", "resource_type", "resource_id"),
                             "device_licenses": ("device_id",), "computer_settings": ("device_id",)}.items():
            identities = [tuple(row[field] for field in fields) for row in self.source[name].values()]
            if len(identities) != len(set(identities)):
                raise HTTPException(422, "같은 장비 연결을 중복으로 포함한 파일은 가져올 수 없습니다.")
        for row in self.source["audit_logs"].values():
            if row["entity_type"] not in {"device", "device_agent", "device_command", "device_license", "computer_setting"}:
                raise HTTPException(422, "장비 이력 외 감사 기록은 가져올 수 없습니다.")

    def issue(self, table, row, code, message):
        self.issues.append({"table": table, "source_id": row["id"], "code": code, "message": message})

    def skip(self, table, row, code="dependency_conflict", message="연결 자료가 일치하지 않아 이 항목을 보류했습니다."):
        self.counts[table]["skip"] += 1
        self.issue(table, row, code, message)

    def keep(self, table, row, target, create=False, values=None):
        ref = Ref(table, row["id"]) if create else target["id"]
        self.mapping[(table, row["id"])] = ref
        self.counts[table]["create" if create else "reuse"] += 1
        self.entries.append({"table": table, "source_id": row["id"], "source_hash": digest(row), "target": ref})
        if create:
            self.actions.append({"table": table, "source_id": row["id"], "values": values, "ref": ref})

    def previous_row(self, table, row):
        prior = self.previous.get((table, row["id"]))
        if prior is None:
            return False
        candidates = [item for item in self.existing[table] if item["id"] == prior["target_id"]]
        if prior["source_hash"] != digest(row) or len(candidates) != 1 or digest(candidates[0]) != prior["target_hash"]:
            self.skip(table, row, "previous_import_changed", "이전에 가져온 원본 또는 운영 자료가 변경되어 자동으로 다시 연결하지 않았습니다.")
        else:
            self.keep(table, row, candidates[0])
        return True

    def mapped(self, table, identifier):
        return None if identifier is None else self.mapping.get((table, identifier))

    def remap(self, row, fields):
        values = {key: value for key, value in row.items() if key != "id"}
        for key, table in fields.items():
            if row[key] is not None:
                value = self.mapped(table, row[key])
                if value is None:
                    return None
                values[key] = value
        return values

    def _match(self, table, row, values, key, historical=False, retain=False):
        if self.previous_row(table, row):
            return
        candidates = [item for item in self.existing[table] if key(item) == key(values)]
        if len(candidates) > 1:
            self.skip(table, row, "ambiguous_match", "일치하는 운영 자료가 여러 건이므로 보류했습니다.")
        elif candidates:
            if retain or digest(_business(candidates[0], historical)) == digest(_business(values, historical)):
                self.keep(table, row, candidates[0])
            else:
                self.skip(table, row, "existing_value_conflict", "운영 자료와 값이 달라 덮어쓰지 않고 보류했습니다.")
        else:
            self.keep(table, row, None, True, values)

    def build(self):
        if self.receipt is not None:
            return self
        for row in self.source["user_refs"].values():
            users = [item for item in self.existing["user_refs"] if normalized(item["email"]) == normalized(row["email"])]
            if len(users) == 1:
                self.keep("user_refs", row, users[0])
            else:
                self.skip("user_refs", row, "historical_actor_unmatched", "이력 작성자는 원래 이름과 원본 번호로 보존하며 운영 사용자를 새로 만들지 않습니다.")
        for name, field in (("asset_categories", "slug"), ("vendors", "name"), ("purchases", "purchase_number")):
            duplicates = Counter(normalized(row[field]) for row in self.source[name].values())
            for row in self.source[name].values():
                if not normalized(row[field]) or duplicates[normalized(row[field])] > 1:
                    self.skip(name, row, "ambiguous_source_identity", "원본의 식별 값이 없거나 중복되었습니다.")
                else:
                    self._match(name, row, _business(row, True), lambda item, field=field: normalized(item[field]), retain=name == "asset_categories")
        asset_keys = Counter(normalized(row["asset_tag"]) for row in self.source["assets"].values())
        for row in self.source["assets"].values():
            if not normalized(row["asset_tag"]) or asset_keys[normalized(row["asset_tag"])] > 1:
                self.skip("assets", row, "ambiguous_source_identity", "원본 자산 번호가 없거나 중복되어 보류했습니다.")
                continue
            if any(row[key] is not None for key in ("assigned_to", "location_id", "department_id", "image_path", "qr_code_path")):
                self.skip("assets", row, "unsupported_parent_dependency", "추가 사용자·위치·첨부파일 연결은 별도 확인이 필요합니다.")
                continue
            values = self.remap(row, {"category_id": "asset_categories", "vendor_id": "vendors"})
            if values is None:
                self.skip("assets", row)
            else:
                self._match("assets", row, values, lambda item: normalized(item["asset_tag"]))
        for row in self.source["software_licenses"].values():
            linked = sum(1 for item in self.source["license_assignments"].values() if item["license_id"] == row["id"])
            if (row["seats_used"] or 0) < linked or (row["seats_total"] is not None and (row["seats_total"] < (row["seats_used"] or 0))):
                self.skip("software_licenses", row, "source_license_capacity_conflict", "원본 라이선스의 사용 수와 장비 연결 수를 먼저 확인해야 합니다.")
                continue
            values = self.remap(row, {"asset_id": "assets", "vendor_id": "vendors"})
            if values is None:
                self.skip("software_licenses", row)
            else:
                self._match("software_licenses", row, values, lambda item: (canonical(item["asset_id"]), item["license_key"], item["license_type"]))
        duplicates = Counter(normalized(row["serial_number"]) for row in self.source["devices"].values())
        reserved_purchases = defaultdict(int)
        for row in self.source["devices"].values():
            previous_target = None
            if self.previous_row("devices", row):
                previous_target = self.mapping.get(("devices", row["id"]))
                if previous_target is None:
                    continue
                # Reusing an unchanged device must still validate newly added
                # parent links in a later batch. Defer the reuse decision until
                # the same dependency/capacity gates have run.
                self.mapping.pop(("devices", row["id"]))
                self.counts["devices"]["reuse"] -= 1
                self.entries = [entry for entry in self.entries if not (entry["table"] == "devices" and entry["source_id"] == row["id"])]
            serial = normalized(row["serial_number"])
            if duplicates[serial] > 1:
                self.skip("devices", row, "ambiguous_source_serial", "원본 시리얼 번호가 중복되어 보류했습니다.")
                continue
            dependencies = [("software_licenses", item["license_id"]) for item in self.source["license_assignments"].values() if item["device_id"] == row["id"]]
            dependencies += [("purchases", item["purchase_id"]) for item in self.source["purchase_allocations"].values() if item["resource_id"] == row["id"]]
            if any(self.mapped(table, identifier) is None for table, identifier in dependencies):
                self.skip("devices", row, "required_parent_held", "라이선스 또는 구매 연결을 보존할 수 없어 장비와 연결 자료를 함께 보류했습니다.")
                continue
            matches = [item for item in self.existing["devices"] if normalized(item["serial_number"]) == serial]
            existing_device_id = matches[0]["id"] if len(matches) == 1 else None
            # Adding assignments to an existing license would require changing
            # its used-seat ledger. That is outside this no-overwrite import.
            license_blocked = False
            for assignment in self.source["license_assignments"].values():
                if assignment["device_id"] != row["id"]:
                    continue
                license_id = self.mapped("software_licenses", assignment["license_id"])
                if isinstance(license_id, int) and not any(item["license_id"] == license_id and item["device_id"] == existing_device_id for item in self.existing["license_assignments"]):
                    license_blocked = True
            if license_blocked:
                self.skip("devices", row, "existing_license_assignment_review", "기존 운영 라이선스의 사용 수 변경이 필요하므로 장비와 연결을 함께 보류했습니다.")
                continue
            purchases_to_reserve = []
            purchase_blocked = False
            for allocation in self.source["purchase_allocations"].values():
                if allocation["resource_id"] != row["id"]:
                    continue
                purchase_id = self.mapped("purchases", allocation["purchase_id"])
                if isinstance(purchase_id, int):
                    already = any(item["purchase_id"] == purchase_id and item["resource_type"] == "device" and item["resource_id"] == existing_device_id for item in self.existing["purchase_allocations"])
                    if already:
                        continue
                    parent = next(item for item in self.existing["purchases"] if item["id"] == purchase_id)
                    used = sum(item["quantity"] for item in self.existing["purchase_allocations"] if item["purchase_id"] == purchase_id)
                else:
                    parent = self.source["purchases"][allocation["purchase_id"]]
                    used = 0
                key = canonical(purchase_id)
                if used + reserved_purchases[key] + allocation["quantity"] > parent["quantity"]:
                    purchase_blocked = True
                purchases_to_reserve.append((key, allocation["quantity"]))
            if purchase_blocked:
                self.skip("devices", row, "purchase_capacity_conflict", "기존 구매 수량을 초과할 수 있어 장비와 구매 연결을 함께 보류했습니다.")
                continue
            if len(matches) > 1 or (not serial and matches and previous_target is None):
                self.skip("devices", row, "ambiguous_target_serial", "운영 시리얼 번호가 중복되었거나 빈 번호가 이미 사용 중입니다.")
            elif matches and matches[0]["device_type"] != row["device_type"]:
                self.skip("devices", row, "device_type_conflict", "같은 시리얼 번호의 장비 종류가 달라 보류했습니다.")
            elif matches:
                self.keep("devices", row, matches[0])
                if digest(_business(matches[0])) != digest(_business(row)):
                    self.issue("devices", row, "existing_device_retained", "같은 시리얼의 기존 운영 장비 정보는 변경하지 않습니다.")
            else:
                self.keep("devices", row, None, True, _business(row, True))
                if not serial:
                    self.manual.append(Ref("devices", row["id"]))
                    self.issue("devices", row, "blank_serial_review", "빈 시리얼 번호를 그대로 보존하고 관리자 확인 알림을 만듭니다.")
            if self.mapped("devices", row["id"]) is not None:
                for key, quantity in purchases_to_reserve:
                    reserved_purchases[key] += quantity
        links = {"device_licenses": {"device_id": "devices"}, "computer_settings": {"device_id": "devices"},
                 "license_assignments": {"device_id": "devices", "license_id": "software_licenses"},
                 "purchase_allocations": {"resource_id": "devices", "purchase_id": "purchases"},
                 "device_usage_history": {"device_id": "devices"}, "ip_change_history": {"device_id": "devices"}}
        for name, fields in links.items():
            for row in self.source[name].values():
                values = self.remap(row, fields)
                if values is None:
                    self.skip(name, row)
                    continue
                if name == "ip_change_history":
                    if row["ip_address_id"] is not None or row["source_type"] not in {"device", "agent"} or row["source_id"] != row["device_id"]:
                        self.skip(name, row, "ip_history_scope_unknown", "장비와의 연결을 확인할 수 없는 IP 이력은 보류했습니다.")
                        continue
                    values["source_id"] = values["device_id"]
                if name in {"device_licenses", "computer_settings"}:
                    key = lambda item: canonical(item["device_id"])
                elif name == "license_assignments":
                    key = lambda item: (canonical(item["device_id"]), canonical(item["license_id"]))
                elif name == "purchase_allocations":
                    key = lambda item: (canonical(item["resource_id"]), canonical(item["purchase_id"]), item["resource_type"])
                else:
                    key = lambda item: digest(_business(item, True))
                self._match(name, row, values, key, historical=name in {"device_usage_history", "ip_change_history"})
        for row in self.source["audit_logs"].values():
            if self.previous_row("audit_logs", row):
                continue
            entity = row["entity_type"]
            source_table = {"device_license": "device_licenses", "computer_setting": "computer_settings"}.get(entity, "devices")
            target = self.mapped(source_table, row["entity_id"])
            if target is None:
                self.skip("audit_logs", row, "audit_scope_held", "안전하게 연결할 장비 또는 하위 자료가 없어 이력을 보류했습니다.")
                continue
            values = _business(row, True)
            values["entity_id"] = target
            values["user_id"] = self.mapped("user_refs", row["user_id"])
            changes = row["changes"]
            changes = dict(changes) if isinstance(changes, dict) else {"original_changes": changes}
            original_scopes = {}
            for field in ("device_id", "previous_device_id", "target_device_id"):
                if field in changes:
                    raw_scope = changes[field]
                    original_scopes[field] = raw_scope
                    source_scope = raw_scope if type(raw_scope) is int else int(raw_scope) if isinstance(raw_scope, str) and raw_scope.isascii() and raw_scope.isdecimal() and str(int(raw_scope)) == raw_scope else None
                    mapped = self.mapped("devices", source_scope)
                    if mapped is None:
                        changes.pop(field)
                    else:
                        changes[field] = mapped
            previous_origin = changes.get("_migration_source")
            changes["_migration_source"] = {"source_id": self.payload["source_id"], "row_id": row["id"],
                "entity_id": row["entity_id"], "user_id": row["user_id"], "action": row["action"],
                "scope_fields": original_scopes, "previous_origin": previous_origin}
            values["changes"] = changes
            # A historical create must not become the new latest-create cutoff,
            # which would hide pre-existing production audit history.
            if row["action"] == "create":
                values["action"] = "history_create"
            self.keep("audit_logs", row, None, True, values)
        self._prune_unused_parents()
        return self

    def _prune_unused_parents(self):
        needed = set()
        by_ref = {item["ref"]: item for item in self.actions}
        def collect(value):
            if isinstance(value, Ref):
                if value in needed:
                    return
                needed.add(value)
                if value in by_ref:
                    collect(by_ref[value]["values"])
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
        for item in self.actions:
            if item["table"] not in PARENTS:
                collect(item["ref"])
        for item in list(self.actions):
            if item["table"] in PARENTS and item["ref"] not in needed:
                self.actions.remove(item)
                self.entries = [entry for entry in self.entries if entry["target"] != item["ref"]]
                self.counts[item["table"]]["create"] -= 1
                self.skip(item["table"], self.source[item["table"]][item["source_id"]], "unused_parent", "가져올 장비에서 사용하지 않는 상위 자료는 추가하지 않습니다.")

    def result(self):
        # Bind all decisions and relevant existing business state. Live agent
        # heartbeats/audit appends do not invalidate a reviewed device plan.
        state = {name: rows for name, rows in self.existing.items() if name not in {"audit_logs", "device_usage_history", "ip_change_history"}}
        state["migration_markers"] = self.marker_rows
        fingerprint = digest({"payload_sha256": self.payload_hash, "state": state, "actions": self.actions, "issues": self.issues})
        summary = {key: sum(item[key] for item in self.counts.values()) for key in ("create", "reuse", "skip")}
        summary["manual_review"] = len(self.manual)
        return {"batch_id": self.payload["batch_id"], "payload_sha256": self.payload_hash,
                "preview_fingerprint": fingerprint, "can_apply": self.receipt is not None or any(entry["table"] == "devices" for entry in self.entries),
                "already_applied": self.receipt is not None, "summary": summary, "tables": self.counts,
                "issues": self.issues, "receipt": self.receipt, "excluded": self.payload["excluded"]}


def preview(connection, payload, payload_hash):
    return Planner(connection, payload, payload_hash).build().result()


def apply_plan(connection, payload, payload_hash, fingerprint, actor, request_ip=None):
    planner = Planner(connection, payload, payload_hash).build()
    result = planner.result()
    if planner.receipt is not None:
        return {**result, "applied": True}
    if fingerprint != result["preview_fingerprint"]:
        raise HTTPException(409, "미리보기 이후 운영 자료가 변경되었습니다. 파일을 다시 미리보기해 주세요.")
    if not result["can_apply"]:
        raise HTTPException(409, "안전하게 추가할 자료가 없습니다. 보류 항목을 확인해 주세요.")
    actual = {}
    def resolve(value):
        if isinstance(value, Ref):
            return actual[value]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value
    def insert(table, values):
        converted = dict(values)
        for name, column in table.columns.items():
            value = converted.get(name)
            if isinstance(value, str) and isinstance(column.type, DateTime):
                converted[name] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif isinstance(value, str) and isinstance(column.type, Date):
                converted[name] = date.fromisoformat(value)
        return connection.execute(table.insert().values(**converted)).inserted_primary_key[0]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for action in planner.actions:
        actual[action["ref"]] = insert(planner.tables[action["table"]], resolve(action["values"]))
        if action["table"] == "devices":
            # SQLite can recycle a deleted highest numeric ID. A new canonical
            # anchor excludes the former device's logs, and is inserted before
            # the incoming historical rows. Reused devices receive no anchor.
            insert(planner.tables["audit_logs"], {"entity_type": "device", "entity_id": actual[action["ref"]],
                "action": "create", "changes": {"source": "device_ledger_migration", "batch_id": payload["batch_id"],
                    "source_id": payload["source_id"], "source_device_id": action["source_id"]},
                "user_id": actor["id"], "user_name": actor["name"], "ip_address": request_ip, "timestamp": now})
    notification = Table("notifications", MetaData(), autoload_with=connection)
    for ref in planner.manual:
        insert(notification, {"type": "device_identity_review", "entity_type": "device", "entity_id": resolve(ref),
                "title": "장비 식별 정보 확인 필요", "message": "가져온 장비의 시리얼 번호가 비어 있습니다. 장비 대장에서 확인해 주세요.",
                "is_read": False, "user_id": actor["id"], "created_at": now})
    receipt = {"batch_id": payload["batch_id"], "payload_sha256": payload_hash, "applied_at": now.isoformat() + "Z",
               "created_counts": {key: value["create"] for key, value in planner.counts.items()},
               "reused_counts": {key: value["reuse"] for key, value in planner.counts.items()},
               "skipped_counts": {key: value["skip"] for key, value in planner.counts.items()}}
    entries = []
    for entry in planner.entries:
        target_id = resolve(entry["target"])
        table = planner.tables[entry["table"]]
        columns = [table.c[key] for key in ("id", "email", "name")] if entry["table"] == "user_refs" else list(table.columns)
        target = _row(connection.execute(select(*columns).where(table.c.id == target_id)).mappings().one())
        entries.append({key: value for key, value in entry.items() if key != "target"} | {"target_id": target_id, "target_hash": digest(target)})
    insert(planner.tables["audit_logs"], {"entity_type": MARKER, "entity_id": 0, "action": "batch_import",
           "changes": {"source_id": payload["source_id"], "batch_id": payload["batch_id"], "payload_sha256": payload_hash,
                       "receipt": receipt, "rows": entries}, "user_id": actor["id"], "user_name": actor["name"],
           "ip_address": request_ip, "timestamp": now})
    return {**result, "applied": True, "receipt": receipt}
