# GCP Cloud Run 배포 가이드

## 🚀 배포 준비사항

### 1. GCP 계정 및 프로젝트 설정
```bash
# Google Cloud CLI 설치 및 로그인
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 필요한 API 활성화
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### 2. 환경변수 설정

**Cloud Run에서 설정해야 할 환경변수들:**

```bash
# 카페24 API 설정 (필수)
CAFE24_CLIENT_ID=your_client_id
CAFE24_CLIENT_SECRET=your_client_secret
CAFE24_ID=your_mall_id
CAFE24_PASSWORD=your_admin_password
CAFE24_REDIRECT_URI=https://your-app-name-xxxx-xx.a.run.app/callback

# API Keys (필수)
SERVICE_KEY=your_flask_secret_key_for_sessions
WEBHOOK_EVENT_KEY=your_webhook_event_key

# 감정 분석 설정 (선택사항 - 기본값 있음)
CONFIDENCE_THRESHOLD=0.7
MODEL_NAME=nlptown/bert-base-multilingual-uncased-sentiment
FALLBACK_MODEL=cardiffnlp/twitter-roberta-base-sentiment-latest

# 모니터링 설정 (선택사항 - 기본값 있음)
CHECK_INTERVAL=3600
MAX_REVIEWS_PER_CHECK=100
NOTIFICATION_ENABLED=true

# 앱 설정 (Cloud Run 자동 설정됨)
DEBUG=false
HOST=0.0.0.0
# PORT는 Cloud Run에서 자동 설정
```

## 🔧 배포 방법

### 방법 1: 자동 배포 스크립트 사용
```bash
chmod +x deploy.sh
./deploy.sh
```

### 방법 2: 수동 배포
```bash
# 1. Docker 이미지 빌드 및 푸시
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/negative-comment-detector

# 2. Cloud Run에 배포
gcloud run deploy negative-comment-detector \
  --image gcr.io/YOUR_PROJECT_ID/negative-comment-detector \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 3600 \
  --concurrency 80 \
  --max-instances 10 \
  --set-env-vars "DEBUG=false,NOTIFICATION_ENABLED=true" \
  --set-secrets "CAFE24_CLIENT_ID=cafe24-client-id:latest,CAFE24_CLIENT_SECRET=cafe24-client-secret:latest"
```

## 🔐 보안 설정

### Secret Manager 사용 (권장)
```bash
# 민감한 정보를 Secret Manager에 저장
echo -n "your_client_id" | gcloud secrets create cafe24-client-id --data-file=-
echo -n "your_client_secret" | gcloud secrets create cafe24-client-secret --data-file=-
echo -n "your_service_key" | gcloud secrets create service-key --data-file=-

# Cloud Run 서비스에 Secret 접근 권한 부여
gcloud run services add-iam-policy-binding negative-comment-detector \
  --member=serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

## 🌐 도메인 설정

### 커스텀 도메인 연결
```bash
# 도메인 매핑
gcloud run domain-mappings create \
  --service negative-comment-detector \
  --domain your-domain.com \
  --region asia-northeast3
```

## 📊 모니터링 설정

### Cloud Logging 및 Monitoring
- 로그: Cloud Run 콘솔에서 자동으로 수집됨
- 메트릭: CPU, 메모리, 응답시간 자동 모니터링
- 알림: Cloud Monitoring으로 알림 설정 가능

## 🔄 CI/CD 파이프라인 (선택사항)

### GitHub Actions 연동
```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloud Run
on:
  push:
    branches: [ main ]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - uses: google-github-actions/setup-gcloud@v0
    - run: gcloud builds submit --tag gcr.io/$PROJECT_ID/negative-comment-detector
    - run: gcloud run deploy --image gcr.io/$PROJECT_ID/negative-comment-detector --platform managed
```

## 💰 비용 최적화

### Cloud Run 요금 최적화 설정
- **메모리**: 1Gi (AI 모델 로딩용)
- **CPU**: 1 (burst 지원)
- **동시성**: 80 (요청 처리량 최적화)
- **최대 인스턴스**: 10 (비용 제한)
- **타임아웃**: 3600초 (AI 모델 로딩 고려)

### 예상 비용
- **무료 티어**: 월 200만 요청, 40만 GB-초, 20만 CPU-초
- **추가 비용**: 초과 시 사용량 기반 과금

## 🚨 문제 해결

### 자주 발생하는 문제들

1. **메모리 부족 오류**
   - 해결: 메모리를 2Gi로 증가
   
2. **타임아웃 오류**
   - 해결: 타임아웃을 3600초로 설정
   
3. **환경변수 오류**
   - 해결: Cloud Run 콘솔에서 환경변수 확인

4. **카페24 OAuth 리다이렉트 오류**
   - 해결: CAFE24_REDIRECT_URI를 Cloud Run URL로 업데이트