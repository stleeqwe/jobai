# JobChat Crawler Dockerfile
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY app/ ./app/

# 환경변수
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# 실행
CMD ["python", "-m", "app.main"]
