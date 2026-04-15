# Auth Agent 가이드

## 역할
Authentik SSO 연동, JWT 토큰 검증, 사용자 인증/인가를 담당한다.

## 인증 플로우
1. 프론트엔드 → `/api/v1/auth/login` → Authentik authorize URL 리다이렉트
2. 사용자 Authentik 로그인
3. Authentik → `/api/v1/auth/callback` (authorization code)
4. 백엔드: code → token 교환 → JWT 검증 (RS256, JWKS)
5. 사용자 자동 생성/업데이트 → access_token 발급
6. 프론트엔드로 리다이렉트 (`/auth/callback?token=xxx`)
7. 프론트엔드: token을 localStorage에 저장

## 핵심 파일
- `backend/app/utils/auth.py` — JWKS 캐싱, verify_token, get_or_create_user
- `backend/app/api/deps.py` — get_current_user, require_admin 의존성
- `backend/app/api/v1/auth.py` — login, callback, /auth/me 엔드포인트
- `frontend/src/stores/auth.ts` — Pinia auth store
- `frontend/src/api/index.ts` — Axios Bearer token 인터셉터

## 환경변수 (`.env`)
```
AUTHENTIK_BASE_URL=https://auth.example.com
AUTHENTIK_CLIENT_ID=xxx
AUTHENTIK_CLIENT_SECRET=xxx
AUTHENTIK_REDIRECT_URI=http://<host>:9918/auth/callback
AUTHENTIK_JWKS_URL=https://auth.example.com/application/o/itam/jwks/
AUTHENTIK_TOKEN_URL=https://auth.example.com/application/o/token/
AUTHENTIK_AUTHORIZE_URL=https://auth.example.com/application/o/authorize/
```

## 권한
- `is_admin: true` → 관리자 전용 기능 (카테고리 CRUD, 사용자 관리 등)
- 일반 사용자 → 자산 조회, 알림 확인
