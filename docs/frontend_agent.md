# Frontend Agent 가이드

## 역할
Vue 3 프론트엔드 UI 개발, 컴포넌트 작성, 상태 관리를 담당한다.

## 기술 스택
- Vue 3 (Composition API + `<script setup>`)
- Vite, TypeScript
- PrimeVue 4 (Aura 테마), PrimeIcons
- Pinia (상태 관리), Vue Router
- Chart.js + vue-chartjs
- Axios (API 통신)

## 구조 규칙
```
frontend/src/
  api/index.ts     → Axios 인스턴스 (Bearer token 자동 첨부)
  types/index.ts   → TypeScript 인터페이스
  router/index.ts  → 라우트 정의 + auth guard
  stores/          → Pinia 스토어 (auth, notification, category)
  layouts/         → DefaultLayout (사이드바 + 탑바)
  views/           → 페이지 컴포넌트 (14개)
```

## 컨벤션
- 한국어 UI only (라벨, 메시지, placeholder 모두 한국어)
- PrimeVue 컴포넌트만 사용, 커스텀 UI 라이브러리 금지
- 각 View에서 필요한 PrimeVue 컴포넌트를 직접 import
- CRUD 패턴: DataTable + Dialog (추가/수정) + Paginator
- Toast로 성공/실패 알림

## 로컬 실행
```bash
cd frontend
npm install
npm run dev  # localhost:3000, API proxy → localhost:8818
```

## 테스트 후 배포
코드 변경 완료 시 `docs/deploy_agent.md` 절차를 따른다.
