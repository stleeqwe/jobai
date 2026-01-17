# JobBot Frontend Dockerfile
# Multi-stage build: Node.js 빌드 → nginx 서빙

FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 설치
COPY package*.json ./
RUN npm ci --only=production=false

# 소스 복사 및 빌드
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# nginx 설정 복사
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 빌드 결과물 복사
COPY --from=builder /app/dist /usr/share/nginx/html

# Cloud Run 포트
EXPOSE 8080

# nginx 실행
CMD ["nginx", "-g", "daemon off;"]
