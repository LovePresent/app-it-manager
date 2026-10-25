# Agent release startup

The production container must stop the previous application before running:

```sh
python scripts/migrate_agent_release.py && python ensure_agent_key.py && python seed_categories.py && uvicorn app.main:app --host 0.0.0.0 --port 8818
```

The guard requires the existing SQLite database at `DATABASE_URL`. It does not
initialize a missing volume. It accepts only the exact known deployed `b856260`
schema, the later `0ac5743` schema, or a known migration revision with its matching
schema. Frozen files contain table definitions only, no business data.

Before any metadata adoption or migration it makes a consistent SQLite backup
and a private manifest in `AGENT_DATABASE_BACKUP_DIR` (default
`data/agent-backups`). It preserves the original migration chain and first applies
the independent inventory prerequisite for older deployments. The final single
head is `20261025_agent_release`. Every pre-existing column value and row count
must match the backup; failures stop startup and retain both database and backup.
There is no automatic downgrade, data reset, backup deletion, or database restore.
Unknown or partially migrated schemas require inspection before another attempt.
The automatic guard is intentionally limited to SQLite; PostgreSQL deployments
require a separately reviewed backup and migration procedure.

Production configuration uses the public origin `https://dev.cqv.kr`,
`AGENT_API_PREFIX=/manage/it/api/v1/agent`, and
`AGENT_DEPLOYMENT_MODE=production`. The dedicated enrollment key stays in the
persistent data volume and must be backed up with that deployment. Do not reuse
the same key for unrelated databases. The public read-only `/agent/ready` endpoint
reports protocol/version/readiness and a nonsecret server identity. Installer
issuance verifies this identity through the configured public endpoint before
writing enrollment state. Development requires explicit opt-in.

# Approved hash-only ticket issuance

`python scripts/issue_agent_ticket.py request.json` or
`python scripts/issue_agent_ticket.py -` (stdin) accepts exactly five string fields:

- `ticketId`: canonical nonzero UUID.
- `tokenHash`: lowercase SHA256 of the **UTF-8 43-character registration token
  string** embedded in the installer, not its decoded bytes.
- `expiresAt`: explicit UTC timestamp in the next 24 hours.
- `expectedServerId`: the verified production readiness fingerprint.
- `issuerEmail`: an existing active administrator's email.

Only an already authorized deployment operator should invoke this administrative
command. It never creates users or accepts the raw token. Successful retries must
match the same hash, issuer and expiry; they do not reset the expiry or duplicate
the audit. Success prints only the ticket UUID. The generated EXE contains a live
bootstrap credential and must not be committed or published as a public artifact.
