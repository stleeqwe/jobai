# JobBot Crawler Dockerfile (V2)
# Cloud Run Jobs용

FROM python:3.11-slim AS builder

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

# 비root 사용자 생성
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# 의존성 복사
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 앱 복사
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser run_crawl_500.py ./

USER appuser

# 환경변수
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Cloud Run Jobs 실행
# --pages: 최대 페이지 수 (기본 500 = 10,000건)
# --workers: 병렬 워커 수 (기본 10)
CMD ["python", "-m", "app.main", "--pages", "500", "--workers", "10"]
