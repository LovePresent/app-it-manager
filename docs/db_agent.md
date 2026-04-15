# DB Agent 가이드

## 역할
데이터베이스 스키마 설계, 마이그레이션 관리, 시드 데이터를 담당한다.

## DB 구성
- **Dev**: SQLite (WAL mode, foreign keys enabled)
- **Prod**: PostgreSQL (DATABASE_URL 환경변수로 전환)

## 모델 구조 (15 파일)
| 파일 | 테이블 |
|------|--------|
| `user.py` | users |
| `category.py` | asset_categories |
| `common.py` | locations, departments, vendors |
| `asset.py` | assets, asset_assignments |
| `license.py` | software_licenses |
| `subscription.py` | cloud_subscriptions |
| `ip_address.py` | ip_addresses |
| `certificate.py` | certificates |
| `consumable.py` | consumable_stocks, consumable_transactions |
| `maintenance.py` | maintenance_records |
| `rack.py` | racks, rack_units |
| `network.py` | network_ports |
| `audit_log.py` | audit_logs |
| `notification.py` | notifications |

## 마이그레이션
```bash
cd backend
# 마이그레이션 생성
alembic revision --autogenerate -m "add column xxx to assets"
# 적용
alembic upgrade head
# 롤백
alembic downgrade -1
```

## 시드 데이터
```bash
cd backend
python seed_categories.py  # 27개 자산 카테고리
```

## 컨벤션
- 모든 모델에 `created_at`, `updated_at` timestamp
- JSON 필드: `custom_fields` (확장 속성)
- 외래키에 인덱스 추가
- 삭제 시 soft delete 고려 (is_active 플래그)
