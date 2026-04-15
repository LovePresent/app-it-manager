# AGENTS.md — IT 자산 관리 시스템

## 프로젝트 개요
IT 장비, 라이센스, 소모품 등을 종합 관리하는 웹 애플리케이션.

## 기술 스택
- **Backend**: Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pydantic 2
- **Frontend**: Vue 3, Vite, TypeScript, PrimeVue 4, Pinia, Chart.js
- **Auth**: Authentik SSO (OIDC, RS256 JWKS)
- **DB**: SQLite (dev) → PostgreSQL (prod), WAL mode
- **Deploy**: Docker Compose, GitHub Actions (SSH)

## 디렉토리 구조
```
backend/
  app/
    main.py           # FastAPI entry, CORS, router registration
    config.py          # Pydantic Settings (.env)
    database.py        # SQLAlchemy engine, session, Base
    models/            # SQLAlchemy ORM models (15 files)
    schemas/           # Pydantic request/response schemas (17 files)
    api/
      deps.py          # Auth dependencies (get_current_user, require_admin)
      v1/              # API route files (18 endpoints)
    services/          # Business logic (audit, asset, notification, export, qr)
    utils/auth.py      # JWKS verification, token decode
  alembic/             # DB migrations
  seed_categories.py   # Seed 27 asset categories
  Dockerfile
  requirements.txt

frontend/
  src/
    main.ts            # Vue app bootstrap (PrimeVue, Pinia, Router)
    api/index.ts       # Axios instance with Bearer token
    types/index.ts     # TypeScript interfaces
    router/index.ts    # Vue Router with auth guard
    stores/            # Pinia stores (auth, notification, category)
    layouts/           # DefaultLayout with sidebar
    views/             # 14 page components
  Dockerfile
  nginx.conf
```

## 컨벤션
- API prefix: `/api/v1/`
- 한국어 UI (Korean only)
- Asset tag format: `IT-YYYY-NNNNN`
- Audit logging on all CUD operations
- PrimeVue components, no custom UI library

## 커맨드
```bash
# 개발 실행
docker compose up --build

# 백엔드만 실행 (개발)
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# 프론트엔드만 실행 (개발)
cd frontend && npm install && npm run dev

# DB 마이그레이션
cd backend && alembic revision --autogenerate -m "description"
cd backend && alembic upgrade head

# 카테고리 시드
cd backend && python seed_categories.py
```

## GitHub Actions Secrets 필요
- `DEV_HOST`: 개발서버 IP
- `DEV_USER`: SSH 유저
- `DEV_SSH_KEY`: SSH 프라이빗 키
- `DEV_APP_PATH`: 서버 내 앱 경로
