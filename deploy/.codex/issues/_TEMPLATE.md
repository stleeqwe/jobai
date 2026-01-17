# 배포 이슈 제목

**ID**: NNN
**생성일**: YYYY-MM-DD
**상태**: `open` | `in_progress` | `resolved` | `failed`
**배포일**: (완료 시 기입)
**관련 이슈**: (있다면)

---

## 1. 배포 개요

- **서비스**: backend / frontend / crawler
- **환경**: dev / staging / prod
- **배포 유형**: 신규 / 업데이트 / 롤백 / 설정변경

---

## 2. 변경 사항

- (변경 내용 요약)
- (관련 커밋/PR)

---

## 3. 사전 체크

### 보안 체크리스트
- [ ] 시크릿이 코드에 노출되지 않음
- [ ] 환경변수가 Secret Manager 사용
- [ ] .env 파일이 gitignore에 포함

### 의존성 체크
- [ ] 로컬 테스트 통과
- [ ] 필요한 시크릿이 Secret Manager에 등록됨
- [ ] 이전 배포 이슈 검토 완료

---

## 4. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: (사용한 키워드)
- 유사 이슈: (있다면 번호)
- 참고 사항: (있다면)

---

## 5. 배포 계획

### 대상 서비스

```
서비스명:
리전: asia-northeast3
플랫폼: Cloud Run (Services / Jobs)
```

### 환경변수

```
ENVIRONMENT=
(시크릿은 Secret Manager 참조)
```

### 실행 명령어

```bash
# 배포 명령어
gcloud run deploy SERVICE_NAME \
  --source . \
  --region asia-northeast3 \
  ...
```

### 롤백 계획

```bash
# 롤백 명령어
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=asia-northeast3
```

---

## 6. 검증

### 실행 결과

| 항목 | 결과 |
|------|------|
| 배포 상태 | 성공 / 실패 |
| 서비스 URL | |
| 리비전 | |
| 빌드 시간 | |

### 헬스체크

```bash
curl -s SERVICE_URL/health
```

```json
(응답 결과)
```

### 로그 확인

```
(주요 로그)
```

---

## 7. 회고

### 문제점 (있다면)
-

### 다음에 참고할 점
-

### 관련 문서 업데이트 필요?
- [ ] 예 → (문서명)
- [ ] 아니오
