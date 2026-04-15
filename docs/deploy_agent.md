# Deploy Agent 가이드

## 역할
코드 변경 후 커밋 → 푸시 → GitHub Actions 배포 → 검증까지 전체 사이클을 수행한다.

## 배포 플로우

### 1. 커밋 & 푸시
```bash
cd D:\CQV-Platform\app\app-it-manager
git add -A
git commit -m "feat/fix: 변경 내용 요약"
git push origin main
```

### 2. GitHub Actions 상태 확인 (필수)
푸시 후 반드시 GitHub Actions 워크플로우 실행 상태를 확인한다.
```bash
# GitHub CLI로 workflow 상태 확인
gh run list --repo LovePresent/app-it-manager --limit 3
gh run view <run-id> --repo LovePresent/app-it-manager
gh run view <run-id> --repo LovePresent/app-it-manager --log-failed
```
- **성공**: 3단계(Docker logs 확인)로 진행
- **실패**: 로그를 분석하고 원인을 파악하여 코드 수정 → 재커밋 → 재푸시

### 3. Docker 로그 확인 (필수)
Actions가 성공해도 컨테이너가 정상 기동됐는지 반드시 확인한다.
서버에 SSH 접속하거나, 로컬 환경이면 직접 확인:
```bash
# 컨테이너 상태
docker compose ps

# 백엔드 로그 (최근 50줄)
docker compose logs --tail 50 backend

# 프론트엔드 로그 (최근 50줄)
docker compose logs --tail 50 frontend

# 헬스체크
curl http://localhost:8818/api/health
```

### 4. 오류 발생 시 대응
| 증상 | 점검 | 조치 |
|------|------|------|
| Actions 실패 | `gh run view --log-failed` | 빌드/SSH 오류 수정 후 re-push |
| 컨테이너 미기동 | `docker compose ps`, `docker compose logs` | Dockerfile, requirements.txt, 환경변수 점검 |
| Backend crash | `docker compose logs backend` | Python import 에러, DB migration 누락 확인 |
| Frontend 502 | `docker compose logs frontend` + nginx error log | nginx.conf proxy 주소, backend 기동 여부 확인 |
| DB 오류 | backend 로그 내 SQLAlchemy 에러 | alembic upgrade head 실행, 스키마 확인 |

### 5. 검증 완료 조건
아래 모두 만족해야 배포 완료로 판단:
- [ ] GitHub Actions 워크플로우 ✅ 성공
- [ ] `docker compose ps` — backend, frontend 모두 `Up` 상태
- [ ] `curl http://<host>:8818/api/health` — 정상 응답
- [ ] `http://<host>:9918` — 프론트엔드 페이지 로딩 확인

## 포트 정보
- Backend: `8818`
- Frontend: `9918`

## Secrets (GitHub Repository)
- `DEV_SERVER_HOST`: 개발서버 IP
- `DEV_SERVER_PORT`: SSH 포트
- `DEV_SERVER_USER`: SSH 유저
- `DEV_SERVER_SSH_KEY`: SSH 프라이빗 키
- `DEV_SERVER_PATH`: 서버 내 앱 경로

## 주의사항
- 절대 `--force` 푸시 금지 (히스토리 보존)
- `.env` 파일은 서버에 직접 관리, 커밋하지 않음
- 배포 실패 시 `git revert`로 롤백 후 재배포
