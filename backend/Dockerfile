# JobChat Backend Dockerfile
FROM python:3.11-slim as builder

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

USER appuser

# 환경변수
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Cloud Run 포트
EXPOSE 8080

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
