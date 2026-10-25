"""Read-only scoped export. Stdout is private payload transport, never a log.

Run only through a wrapper which captures stdout directly into an access-checked
private file. This script never reads agent credentials, tickets or commands.
"""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

ORDER = ("user_refs", "asset_categories", "vendors", "assets", "software_licenses", "purchases", "devices",
         "device_licenses", "computer_settings", "license_assignments", "purchase_allocations",
         "device_usage_history", "ip_change_history", "audit_logs")


def rows(db, table, where="", parameters=()):
    columns = {row[1]: row[2].upper() for row in db.execute('PRAGMA table_info("' + table + '")')}
    results = []
    for raw in db.execute('SELECT * FROM "' + table + '"' + (" WHERE " + where if where else "") + ' ORDER BY id', parameters):
        row = dict(raw)
        for name, value in row.items():
            if value is not None and columns[name] == "JSON":
                row[name] = json.loads(value) if isinstance(value, str) else value
            elif value is not None and columns[name] in {"DATETIME", "TIMESTAMP"}:
                row[name] = datetime.fromisoformat(value).isoformat()
            elif value is not None and columns[name] == "BOOLEAN":
                row[name] = bool(value)
        results.append(row)
    return results


def selected(db, table, ids):
    if not ids:
        return []
    return rows(db, table, "id IN (" + ",".join("?" for _ in ids) + ")", sorted(ids))


def export(db, source_id, batch_id=None):
    UUID(source_id)
    db.row_factory = sqlite3.Row
    data = {name: [] for name in ORDER}
    data["devices"] = rows(db, "devices")
    device_ids = {row["id"] for row in data["devices"]}
    for name in ("device_licenses", "computer_settings", "device_usage_history", "license_assignments", "ip_change_history"):
        data[name] = [row for row in rows(db, name) if row["device_id"] in device_ids]
    data["purchase_allocations"] = [row for row in rows(db, "purchase_allocations") if row["resource_type"] == "device" and row["resource_id"] in device_ids]
    data["software_licenses"] = selected(db, "software_licenses", {row["license_id"] for row in data["license_assignments"]})
    data["assets"] = selected(db, "assets", {row["asset_id"] for row in data["software_licenses"]})
    data["asset_categories"] = selected(db, "asset_categories", {row["category_id"] for row in data["assets"]})
    data["vendors"] = selected(db, "vendors", {row["vendor_id"] for row in data["assets"] + data["software_licenses"] if row["vendor_id"] is not None})
    data["purchases"] = selected(db, "purchases", {row["purchase_id"] for row in data["purchase_allocations"]})
    # Refuse silently losing additional parent dependencies not in this bounded
    # transfer. The actual source audit must confirm these are absent first.
    if any(any(row[key] is not None for key in ("assigned_to", "location_id", "department_id", "image_path", "qr_code_path")) for row in data["assets"]):
        raise ValueError("Unsupported parent assignment/location/file dependency; no export produced.")
    asset_ids = {row["id"] for row in data["assets"]}
    license_ids = {row["id"] for row in data["software_licenses"]}
    if any(row["asset_id"] in asset_ids for row in rows(db, "asset_assignments")):
        raise ValueError("Parent asset assignment history requires separate handling.")
    if any(row["license_id"] in license_ids for row in rows(db, "software_license_photos")):
        raise ValueError("Parent license attachments require separate handling.")
    audit = rows(db, "audit_logs", "entity_type IN ('device','device_agent','device_command','device_license','computer_setting')")
    cutoff = {}
    for row in audit:
        if row["entity_type"] == "device" and row["action"] == "create":
            cutoff[row["entity_id"]] = max(cutoff.get(row["entity_id"], 0), row["id"])
    children = {"device_license": {row["id"]: row for row in data["device_licenses"]},
                "computer_setting": {row["id"]: row for row in data["computer_settings"]}}
    excluded = {"unmatched_or_previous_device_audits": 0, "unproven_child_audits": 0,
                "active_agents_credentials_tickets_commands": "not read or exported"}
    for row in audit:
        if row["entity_type"] in {"device", "device_agent", "device_command"}:
            if row["entity_id"] in device_ids and row["id"] >= cutoff.get(row["entity_id"], 0):
                data["audit_logs"].append(row)
            else:
                excluded["unmatched_or_previous_device_audits"] += 1
        else:
            child = children[row["entity_type"]].get(row["entity_id"])
            changes = row["changes"] if isinstance(row["changes"], dict) else {}
            if child and changes.get("device_id") == child["device_id"] and row["id"] >= cutoff.get(child["device_id"], 0):
                data["audit_logs"].append(row)
            else:
                excluded["unproven_child_audits"] += 1
    actors = {row["user_id"] for row in data["audit_logs"] if row["user_id"] is not None}
    if actors:
        data["user_refs"] = [dict(row) for row in db.execute(
            "SELECT id,email,name FROM users WHERE id IN (" + ",".join("?" for _ in actors) + ") ORDER BY id", sorted(actors))]
    return {"format": "itam-device-ledger-v1", "source_id": source_id, "batch_id": batch_id or str(uuid4()),
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "tables": data, "excluded": excluded}


def main():
    from sqlalchemy.engine import make_url
    from app.config import settings
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", required=True)
    args = parser.parse_args()
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ValueError("Expected existing SQLite source.")
    path = Path(url.database).resolve()
    if not path.is_file():
        raise ValueError("Source database does not exist.")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("BEGIN")
        payload = export(db, args.source_id)
        db.rollback()
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
