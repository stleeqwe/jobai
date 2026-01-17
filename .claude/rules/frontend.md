---
paths:
  - "frontend/**/*.ts"
  - "frontend/**/*.tsx"
---

# Frontend Rules

`frontend/` 디렉토리의 TypeScript/React 코드 작업 시 적용되는 규칙입니다.

## 필수 규칙

### 1. Tailwind CSS 사용 (inline style 금지)
```tsx
// CORRECT
<div className="flex items-center gap-2 p-4 bg-white rounded-lg shadow">
  <span className="text-gray-700 font-medium">{title}</span>
</div>

// WRONG - inline style 절대 금지
<div style={{ display: 'flex', padding: '16px' }}>
  <span style={{ color: '#374151' }}>{title}</span>
</div>
```

### 2. 함수형 컴포넌트 + Hooks
```tsx
// CORRECT
const JobCard: React.FC<JobCardProps> = ({ job }) => {
  const [expanded, setExpanded] = useState(false);
  return <div>...</div>;
};

// WRONG - 클래스 컴포넌트 사용 금지
class JobCard extends React.Component { ... }
```

### 3. Props Interface 정의
```tsx
interface JobCardProps {
  job: JobItem;
  onSelect?: (id: string) => void;
}

const JobCard: React.FC<JobCardProps> = ({ job, onSelect }) => {
  ...
};
```

### 4. any 타입 최소화
```tsx
// CORRECT
const [jobs, setJobs] = useState<JobItem[]>([]);

// WRONG
const [jobs, setJobs] = useState<any>([]);
```

## 컴포넌트 구조

```
src/
├── components/     # UI 컴포넌트
├── hooks/          # Custom Hooks
├── services/       # API 호출
├── types/          # TypeScript 타입
└── App.tsx         # 메인 앱
```

## 상태 관리 패턴

| 상황 | 사용 |
|------|------|
| 로컬 상태 | useState |
| 복잡한 로직 | useReducer |
| 부수 효과 | useEffect |
| API 호출 | useChat (커스텀 훅) |

## API 호출

`services/api.ts` 사용:
```tsx
import { sendMessage, loadMoreJobs } from '../services/api';

// useChat 훅에서 관리
const { messages, sendMessage, loadMore } = useChat();
```

## 개발 명령어

```bash
npm run dev      # 개발 서버
npm run build    # 빌드
npm run lint     # 린트
npm run test     # 테스트
```

## Vite 포트 주의

포트 충돌 시 자동 변경: 5173 → 5174 → 5175 ...

백엔드 CORS와 불일치 시 통신 오류 발생!
→ `backend/.env`의 `ALLOWED_ORIGINS` 확인

## 금지 사항

- inline style 사용 금지
- any 타입 남용 금지
- 클래스 컴포넌트 사용 금지
- 직접 fetch 대신 api.ts 서비스 사용
