# Python 3.11 slim 이미지 사용 (Cloud Run에 최적화)
FROM python:3.11-slim

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# requirements.txt 먼저 복사 (도커 레이어 캐싱 최적화)
COPY requirements.txt .

# Python 패키지 설치 (메모리 최적화)
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# 애플리케이션 코드 복사
COPY . .

# 포트 설정 (Cloud Run은 환경변수 PORT 사용)
ENV PORT=8080

# 비관리자 사용자 생성 및 권한 설정 (보안)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run용 헬스체크
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$PORT/ || exit 1

# Gunicorn으로 프로덕션 서버 실행 (메모리 최적화)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 0 \
    --max-requests 1000 --max-requests-jitter 100 \
    --preload main:app