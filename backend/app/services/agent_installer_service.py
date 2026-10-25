"""Build per-device installers on Linux from verified, credential-free Windows templates."""
import base64
import hashlib
import json
import re
import struct
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from app.services.agent_connection_service import LATEST_AGENT_VERSION, validate_connection

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / 'agent_package'


def _asset(name: str, manifest: dict) -> bytes:
    path = PACKAGE_ROOT / name
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise HTTPException(503, '에이전트 설치 패키지가 준비되지 않았습니다.') from exc
    expected = manifest.get('sha256', {}).get(name)
    if not expected or hashlib.sha256(content).hexdigest() != expected:
        raise HTTPException(503, '에이전트 설치 패키지 무결성 검증에 실패했습니다.')
    return content


def _verified_package():
    try:
        manifest = json.loads((PACKAGE_ROOT / 'manifest.json').read_text(encoding='utf-8-sig'))
        if manifest.get('version') != LATEST_AGENT_VERSION:
            raise ValueError('Installer package version mismatch')
        names = ('install.template.ps1', 'agent.ps1', 'uninstall.ps1', 'SecurityPresenceService.exe', 'SetupTemplate.exe')
        assets = {name: _asset(name, manifest) for name in names}
        script = assets['install.template.ps1'].decode('utf-8-sig')
        for marker in ('__CONFIG_BASE64__', '__AGENT_BASE64__', '__UNINSTALL_BASE64__', '__SERVICE_BASE64__'):
            if marker not in script:
                raise ValueError('Missing installer marker')
        for name in ('SecurityPresenceService.exe', 'SetupTemplate.exe'):
            content = assets[name]
            if len(content) < 256 or content[:2] != b'MZ':
                raise ValueError('Invalid PE template')
            offset = int.from_bytes(content[0x3c:0x40], 'little')
            if offset < 0x40 or offset + 4 > len(content) or content[offset:offset + 4] != b'PE\0\0':
                raise ValueError('Invalid PE header')
        return manifest, assets
    except HTTPException:
        raise
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(503, '현재 버전의 에이전트 설치 패키지가 준비되지 않았습니다.') from exc


def verify_package_ready():
    _verified_package()


def build_agent_installer(config: dict, device_name: str, format: str = 'exe') -> tuple[str, bytes, str]:
    if format != 'exe':
        raise HTTPException(422, '지원하지 않는 설치 파일 형식입니다.')
    try:
        validate_connection(config['serverUrl'], config.get('apiPrefix'), config.get('deploymentMode'))
        if not re.fullmatch(r'[0-9a-f]{64}', config.get('expectedServerId', '')):
            raise ValueError()
        automatic = config.get('registrationMode') == 'automatic'
        identity = config['ticketId'] if automatic else config['deviceId']
        UUID(identity)
        if config.get('heartbeatIntervalSeconds') != 15:
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', config.get('registrationToken' if automatic else 'enrollmentToken', '')):
            raise ValueError()
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(422, '에이전트 연결 설정이 올바르지 않습니다.') from exc
    try:
        manifest, assets = _verified_package()
        script = assets['install.template.ps1'].decode('utf-8-sig')
        replacements = {
            '__CONFIG_BASE64__': json.dumps(config, ensure_ascii=True, separators=(',', ':')).encode(),
            '__AGENT_BASE64__': assets['agent.ps1'],
            '__UNINSTALL_BASE64__': assets['uninstall.ps1'],
            '__SERVICE_BASE64__': assets['SecurityPresenceService.exe'],
        }
        for marker, content in replacements.items():
            if marker not in script:
                raise ValueError('Missing installer marker')
            script = script.replace(marker, base64.b64encode(content).decode('ascii'))
        script_bytes = ('\ufeff' + script).encode('utf-8')
        version = manifest['version']
        prefix = 'Auto' if automatic else 'Agent'
        stem = f"App-IT-Manager-{prefix}-{identity[:8]}-{version}"
        executable = assets['SetupTemplate.exe']
        if executable[:2] != b'MZ':
            raise ValueError('Invalid PE template')
        safe_name = re.sub(r'[\r\n\x00]', ' ', str(device_name))[:200]
        display = f"{config['serverUrl']}\n{safe_name}\n".encode('utf-8')
        if not 100 <= len(script_bytes) <= 4 * 1024 * 1024 or not 1 <= len(display) <= 4096:
            raise ValueError('Invalid payload size')
        payload = script_bytes + display
        footer = hashlib.sha256(payload).digest() + struct.pack('<II', len(script_bytes), len(display)) + b'SPSETUP1'
        return stem + '.exe', executable + payload + footer, 'application/vnd.microsoft.portable-executable'
    except HTTPException:
        raise
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as exc:
        raise HTTPException(503, '에이전트 설치 패키지를 생성하지 못했습니다.') from exc
