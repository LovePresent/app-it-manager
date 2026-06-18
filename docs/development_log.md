# IT Manager 개발일지

작성 기준: Git 커밋 이력, 현재 작업트리 변경 내역, 로컬 WSL Docker 검증 결과.

## 2026-04-15

### 초기 구현
- FastAPI 백엔드와 Vue 3/Vite 프론트엔드 기반 IT 자산 관리 시스템 초기 구현.
- 백엔드 포트 `8818`, 프론트엔드 포트 `9918` 기준 Docker 배포 구조 구성.
- 자산, 라이센스, 구독, IP, 인증서, 소모품, 유지보수, 랙, 알림, 감사 로그 등 기본 도메인 API와 화면 구성.
- QR 코드 생성, 엑셀 import/export, 기본 대시보드 통계 기능 구성.

### 배포/운영 문서화
- GitHub Actions 배포 워크플로우와 서버 배포 절차 정리.
- `docs/deploy_agent.md`, `docs/backend_agent.md`, `docs/frontend_agent.md`, `docs/db_agent.md`, `docs/auth_agent.md` 작성.
- `AGENTS.md`에 프로젝트 구조, 기술 스택, 주요 명령, 에이전트 가이드 링크 정리.

### CI/CD 수정
- GitHub Actions secret 이름을 `DEV_SERVER_*` 규칙으로 정리.
- 배포 후 `docker compose ps`, 로그, 헬스체크를 확인하는 post-deploy 검증 추가.
- 서버에 저장소가 없을 때 자동 clone하는 절차 추가.
- `.env.example` 기반 `.env` 자동 생성 플로우 추가.

## 2026-04-17

### 인증/라우팅 안정화
- Vite base path와 Vue Router base를 `/manage/it/` 기준으로 조정.
- Axios/login redirect 경로를 `/manage/it/` 배포 경로에 맞게 수정.
- Authentik authorize 요청에서 `redirect_uri` URL 인코딩 문제 수정.
- `tsconfig` 관련 빌드 오류와 불필요 import 정리.

## 2026-04-29

### 로컬 로그인 및 인증 개선
- 로컬 개발용 로그인 API와 설정 추가.
- Authentik SSO 외에도 로컬 개발 환경에서 관리자로 접근할 수 있도록 `LOCAL_LOGIN_*` 설정 흐름 구성.
- 프론트 로그인 화면과 API 인증 흐름 정리.

### IP / MAC 관리 고도화
- IP 주소 모델과 스키마 확장.
- IP/MAC 변경 이력 마이그레이션 추가: `20260429_add_ip_change_history.py`.
- IP 주소 화면에 검색, 그룹핑, 변경 이력 표시, 상태 필터 흐름 추가.

### 디바이스/보안/라이센스 관리 확장
- 디바이스 인벤토리 모델, 스키마, API 추가.
- 컴퓨터 설정 화면 추가: Windows 보안 설정 적용 상태 관리.
- 디바이스 라이센스 화면 추가: 한글, MS Office, CAD, DLP, AV, EDR 등 사용자별 설치/보안 라이센스 관리.
- AI 사용 구독 API와 화면 추가.

### 기존 화면 정리
- 자산, 인증서, 소모품, 유지보수, 랙, 카테고리, 라이센스, 구독 화면을 새 API 응답 구조에 맞게 정리.
- 네비게이션 데이터 기반 메뉴/검색 구조 도입.

## 2026-04-30

### 조직/위치 및 디바이스 운영 기능
- 위치/부서 API와 화면 추가.
- 디바이스 화면 고도화.
- 사용자, 사번, 부서, 위치, 공장, 장비 종류, 보안 설정, 라이센스 요약을 한 화면에서 확인하도록 구성.
- 디바이스 변경, 재배정, 교체, 사용 이력 기록 흐름 추가.
- 일괄 변경 기능 추가: 부서, 위치, 공장, 상태, 장비 사양, 보안 설정을 선택 적용.

## 2026-05-08

### 사용자/연구노트 기능 작업
- 사용자 목록 조회 API 추가.
- 연구노트(ELN) 관련 모델, 스키마, API, 첨부파일, 전자서명, PDF export 기능이 추가되었음.

## 2026-05-11

### 연구노트 기능 제거
- 요청에 따라 IT Manager에서 연구노트 기능 제거.
- 백엔드 `research_notes` 라우터 등록 제거.
- 연구노트 모델, 스키마, API, PDF export service, Alembic 마이그레이션 삭제.
- 프론트 `/research-notes` 라우트, 메뉴, 검색 항목, 타입 정의, 감사 로그 필터 항목 제거.
- 검증:
  - `npm.cmd run build` 성공.
  - `/api/v1/research-notes` 404 확인.
  - OpenAPI와 소스 검색에서 연구노트 관련 참조 제거 확인.

### 구매 리스트 / 배분 리스트 메뉴 추가
- `구매 리스트` 메뉴 추가: `/purchased-devices`.
- `배분 리스트` 메뉴 추가: `/distributed-devices`.
- 공통 화면 `DeviceListReportView.vue` 추가.
- 구매 리스트는 `purchase_date`가 등록된 디바이스 기준으로 조회.
- 배분 리스트는 현재 `assigned` 상태인 디바이스 기준으로 조회.
- 백엔드 `/devices` API에 `has_purchase_date=true|false` 필터 추가.
- 네비게이션, 상단 메뉴, 사이드 메뉴, 통합 메뉴 검색에 신규 메뉴 등록.
- 검증:
  - `npm.cmd run build` 성공.
  - `GET /api/v1/devices?has_purchase_date=true&page=1&size=1` 200 확인.
  - `GET /api/v1/devices?status=assigned&page=1&size=1` 200 확인.
  - `/manage/it/purchased-devices`, `/manage/it/distributed-devices` 200 확인.

### WSL Docker 기준 정리
- 로컬 기본 실행/검증 환경이 WSL Ubuntu Docker임을 확인.
- 실행 중인 컨테이너:
  - `itam-local-backend`: `8818`
  - `itam-local-frontend`: `3000`
- `compose.local.yaml`이 bind mount, `uvicorn --reload`, Vite dev server 기반이라 일반 소스 변경은 재빌드 없이 반영되는 구조임을 확인.
- `docs/deploy_agent.md`에 WSL Ubuntu Docker를 기본 로컬 Docker 환경으로 명시.
- `AGENTS.md`의 개발 실행/로그 확인 명령도 WSL Ubuntu Docker 기준으로 수정.

### IP 대역 / VLAN 구성 보기 추가
- IP/MAC 화면에 `10.공장.VLAN.사용자NO` 규칙 기반 대역 보기 추가.
- `10.1.x.x`는 1공장, `10.2.x.x`는 2공장, `10.3.x.x`는 3공장으로 해석.
- IP 3번째 옥텟을 VLAN, 4번째 옥텟을 사용자NO로 표시.
- 공장별 요약, VLAN(부서)별 대역 요약, 대역별 IP 상세 표를 추가.
- VLAN 대역은 부서명과 함께 그룹핑하고 부서 필터를 제공하도록 정리.
- 디바이스 IP와 IP 주소 대장을 합산해 대역/VLAN 현황을 표시.
- 검증:
  - `npm.cmd run build` 성공.
  - WSL Docker 프론트 dev server HMR 로그에서 `IPAddressesView.vue` 반영 확인.
  - `/manage/it/ip-addresses` 200 확인.

## 현재 검증 상태

- 프론트엔드 타입 체크 및 프로덕션 빌드: `npm.cmd run build` 성공.
- 로컬 백엔드 헬스체크: `http://localhost:8818/api/health` 정상.
- 로컬 프론트엔드 개발 서버: `http://localhost:3000/manage/it/` 정상.
- WSL Docker compose 상태:
  - `backend` Up
  - `frontend` Up

## 남은 확인 사항

- 현재 작업트리에는 여러 기능 파일이 커밋되지 않은 상태로 남아 있음.
- 운영 배포가 필요하면 `docs/deploy_agent.md` 기준으로 커밋, 푸시, GitHub Actions, Docker 로그 확인까지 진행해야 함.
