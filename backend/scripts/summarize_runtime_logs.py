"""Print fixed diagnostic counters without exporting request URLs or row values."""
import json
import re
import sys

log = sys.stdin.read()
errors = ("OperationalError", "ProgrammingError", "no such column", "does not exist")
network_errors = ("ConnectTimeout", "ReadTimeout", "ConnectError", "HTTPStatusError", "JSONDecodeError")
print(json.dumps({
    "database_preservation_confirmed": bool(re.search(r'"existing_values_preserved"\s*:\s*true', log)),
    "database_errors": {name: log.count(name) for name in errors},
    "connection_errors": {name: log.count(name) for name in network_errors},
}))
