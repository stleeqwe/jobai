# IPRoyal 프록시 설정 가이드

> 작성일: 2026-01-16
> 참조: https://docs.iproyal.com/proxies/residential/proxy/rotation

## 1. 기본 정보

| 항목 | 값 |
|-----|---|
| 서비스 | IPRoyal Residential Proxy |
| Host | geo.iproyal.com |
| Port | 12321 |
| 인증 | HTTP Basic (Username:Password) |
| 동시 연결 | **무제한** |
| 트래픽 만료 | 없음 (구매 후 영구) |

## 2. 세션 타입

### 2.1 Random (매 요청 새 IP)

**용도:** 익명성 필요, 스크래핑

**형식:**
```
username:password@geo.iproyal.com:12321
```

**옵션:**
- `_forcerandom-1`: IP 로테이션 감소, 위치 풀 확대

### 2.2 Sticky (고정 IP 유지)

**용도:** 세션 유지, 로그인 필요 작업

**형식:**
```
username:password_session-{SESSION_ID}_lifetime-{DURATION}@geo.iproyal.com:12321
```

**파라미터:**

| 파라미터 | 설명 | 예시 |
|---------|-----|-----|
| `session` | 세션 식별자 (정확히 8자 영숫자) | `worker01` |
| `lifetime` | 세션 유지 시간 | `10m`, `1h`, `7d` |

**시간 단위:**
- `s`: 초 (최소 1초)
- `m`: 분
- `h`: 시간
- `d`: 일 (최대 7일)

## 3. 프로젝트 적용

### 3.1 현재 설정

**파일:** `crawler/app/core/session_manager.py`

```python
PROXY_HOST = "geo.iproyal.com"
PROXY_PORT = 12321
PROXY_USERNAME = "wjmD9FjEss6TCmTC"
PROXY_PASSWORD = "PFZsSKOcUmfIb0Kj"
```

### 3.2 워커별 세션 분리

```python
def get_proxy_url_with_session(worker_id: int, lifetime: str = "10m") -> str:
    """워커별 고정 IP 프록시 URL 생성"""
    session_id = f"worker{worker_id:02d}"  # worker01, worker02, ...
    return (
        f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}"
        f"_session-{session_id}_lifetime-{lifetime}"
        f"@{PROXY_HOST}:{PROXY_PORT}"
    )

# 사용 예시
for i in range(10):
    proxy_url = get_proxy_url_with_session(i, "10m")
    # http://user:pass_session-worker00_lifetime-10m@geo.iproyal.com:12321
```

### 3.3 랜덤 IP (목록 수집용)

```python
def get_random_proxy_url() -> str:
    """매 요청 새 IP 프록시 URL"""
    return f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
```

## 4. 적용 전략

| 작업 | 세션 타입 | 워커 수 | 세션 수명 |
|-----|---------|--------|---------|
| 목록 수집 (AJAX) | Random | 1 | - |
| 상세 수집 | Sticky | 10 | 10분 |
| 연결 테스트 | Random | 1 | - |

## 5. 차단 대응

### 차단 징후
- HTTP 403 Forbidden
- HTTP 429 Too Many Requests
- "captcha", "보안문자" 텍스트

### 대응 방법

| 상황 | 대응 |
|-----|------|
| 단일 워커 차단 | 해당 세션 ID 변경 |
| 전체 차단 | 요청 간격 증가 (300ms → 500ms) |
| 지속 차단 | 워커 수 감소 (10 → 5) |

## 6. 비용 참고

- **트래픽 기반 과금**: GB당 과금
- **세션 수 무제한**: 추가 비용 없음
- **만료 없음**: 구매한 트래픽 영구 사용

## 7. 테스트 명령어

```bash
# 프록시 연결 테스트
curl -x http://user:pass@geo.iproyal.com:12321 https://ipinfo.io/ip

# Sticky 세션 테스트 (같은 IP 유지 확인)
curl -x "http://user:pass_session-test1234_lifetime-5m@geo.iproyal.com:12321" https://ipinfo.io/ip
curl -x "http://user:pass_session-test1234_lifetime-5m@geo.iproyal.com:12321" https://ipinfo.io/ip
```

## 변경 이력

| 날짜 | 내용 |
|-----|-----|
| 2026-01-16 | 초안 작성 |
