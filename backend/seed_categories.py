"""Seed 27 asset categories for IT asset management."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
from app.models.category import AssetCategory

# Import all models to register them
from app.models import user, common, asset, license, subscription
from app.models import ip_address, certificate, consumable, maintenance
from app.models import rack, network, audit_log, notification

CATEGORIES = [
    {"name": "PC/서버", "slug": "pc-server", "icon": "pi pi-server", "sort_order": 1},
    {"name": "노트북", "slug": "laptop", "icon": "pi pi-desktop", "sort_order": 2},
    {"name": "모니터/디스플레이", "slug": "monitor", "icon": "pi pi-image", "sort_order": 3},
    {"name": "모바일 기기", "slug": "mobile", "icon": "pi pi-mobile", "sort_order": 4},
    {"name": "프린터/복합기", "slug": "printer", "icon": "pi pi-print", "sort_order": 5},
    {"name": "네트워크 장비", "slug": "network", "icon": "pi pi-sitemap", "sort_order": 6},
    {"name": "보안 장비", "slug": "security-device", "icon": "pi pi-shield", "sort_order": 7},
    {"name": "UPS/전원 장비", "slug": "ups-power", "icon": "pi pi-bolt", "sort_order": 8},
    {"name": "CCTV/보안카메라", "slug": "cctv", "icon": "pi pi-video", "sort_order": 9},
    {"name": "회의실 장비", "slug": "meeting-room", "icon": "pi pi-users", "sort_order": 10},
    {"name": "주변기기", "slug": "peripheral", "icon": "pi pi-th-large", "sort_order": 11, "description": "키보드, 마우스, 헤드셋 등"},
    {"name": "외장 저장장치", "slug": "external-storage", "icon": "pi pi-database", "sort_order": 12, "description": "USB, 외장HDD 등"},
    {"name": "충전기/어댑터/독", "slug": "charger-dock", "icon": "pi pi-plug", "sort_order": 13},
    {"name": "소프트웨어 라이센스", "slug": "software-license", "icon": "pi pi-key", "sort_order": 14},
    {"name": "소프트웨어 미디어", "slug": "software-media", "icon": "pi pi-disc", "sort_order": 15, "description": "설치CD, USB키 등"},
    {"name": "SaaS/클라우드 구독", "slug": "saas-cloud", "icon": "pi pi-cloud", "sort_order": 16},
    {"name": "IP 주소", "slug": "ip-address", "icon": "pi pi-globe", "sort_order": 17},
    {"name": "SSL 인증서/도메인", "slug": "certificate", "icon": "pi pi-lock", "sort_order": 18},
    {"name": "소모품", "slug": "consumable", "icon": "pi pi-box", "sort_order": 19, "description": "토너, 케이블, 배터리 등"},
    {"name": "케이블/패치", "slug": "cable-patch", "icon": "pi pi-link", "sort_order": 20},
    {"name": "서버 랙", "slug": "server-rack", "icon": "pi pi-table", "sort_order": 21},
    {"name": "스토리지/NAS/SAN", "slug": "storage-nas", "icon": "pi pi-database", "sort_order": 22},
    {"name": "전화/VoIP", "slug": "voip-phone", "icon": "pi pi-phone", "sort_order": 23},
    {"name": "IoT/센서", "slug": "iot-sensor", "icon": "pi pi-wifi", "sort_order": 24},
    {"name": "가상머신/컨테이너", "slug": "vm-container", "icon": "pi pi-clone", "sort_order": 25},
    {"name": "백업 장비/미디어", "slug": "backup-media", "icon": "pi pi-save", "sort_order": 26},
    {"name": "사이니지/디스플레이", "slug": "signage", "icon": "pi pi-window-maximize", "sort_order": 27},
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(AssetCategory).count()
        if existing > 0:
            print(f"Categories already seeded ({existing} found). Skipping.")
            return

        for cat in CATEGORIES:
            db.add(AssetCategory(**cat))
        db.commit()
        print(f"Seeded {len(CATEGORIES)} categories successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
