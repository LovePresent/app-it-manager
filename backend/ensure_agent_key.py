"""Provision a persistent private key for automatic-enrollment replay only.
This is not a Windows code-signing certificate and never changes SSO secrets.
"""
import os
from pathlib import Path
from app.config import settings

if settings.AGENT_ENROLLMENT_SECRET:
    if len(settings.AGENT_ENROLLMENT_SECRET.encode()) < 32:
        raise RuntimeError('AGENT_ENROLLMENT_SECRET must contain at least 32 bytes')
    print('Automatic enrollment key: environment configured.')
else:
    destination = Path(settings.AGENT_ENROLLMENT_SECRET_FILE)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if len(destination.read_bytes()) < 32:
            raise RuntimeError('Existing automatic enrollment key is invalid; refusing to replace it.')
        print('Automatic enrollment key: existing persistent key preserved.')
    else:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(os.urandom(32))
            stream.flush()
            os.fsync(stream.fileno())
        print('Automatic enrollment key: private persistent key created.')
