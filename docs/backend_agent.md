# Backend Agent 가이드

## 역할
FastAPI 백엔드 코드 작성, API 설계, DB 모델, 비즈니스 로직 개발을 담당한다.

## 기술 스택
- Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2
- Alembic (DB 마이그레이션)
- SQLite (dev) / PostgreSQL (prod)

## 구조 규칙
```
backend/app/
  models/       → SQLAlchemy ORM 모델 (1 모델 = 1 파일)
  schemas/      → Pydantic 스키마 (Base/Create/Update/Response 패턴)
  api/v1/       → 라우트 핸들러 (1 리소스 = 1 파일)
  services/     → 비즈니스 로직 (audit, asset, notification, export, qr)
  utils/        → 유틸리티 (auth.py)
```

## 컨벤션
- API prefix: `/api/v1/`
- 모든 CUD 작업에 audit log 기록
- 자산 태그: `IT-YYYY-NNNNN` 자동 생성
- 인증: Authentik OIDC → JWT 검증 (`api/deps.py`)
- 에러 응답: `HTTPException` 사용, 한국어 메시지

## DB 마이그레이션
```bash
cd backend
alembic revision --autogenerate -m "설명"
alembic upgrade head
```

## 로컬 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8818
```

## 테스트 후 배포
코드 변경 완료 시 `docs/deploy_agent.md` 절차를 따른다.
