#!/bin/bash

# GCP Cloud Run 자동 배포 스크립트
# 사용법: ./deploy.sh [PROJECT_ID] [SERVICE_NAME] [REGION]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 기본값 설정
DEFAULT_PROJECT_ID="hurdlers-web"
DEFAULT_SERVICE_NAME="cilantro-comment-detector"
DEFAULT_REGION="asia-northeast3"

# 파라미터 받기
PROJECT_ID=${1:-$DEFAULT_PROJECT_ID}
SERVICE_NAME=${2:-$DEFAULT_SERVICE_NAME}
REGION=${3:-$DEFAULT_REGION}

echo -e "${BLUE}🚀 Cloud Run 배포 시작...${NC}"
echo -e "프로젝트: ${GREEN}$PROJECT_ID${NC}"
echo -e "서비스: ${GREEN}$SERVICE_NAME${NC}"
echo -e "지역: ${GREEN}$REGION${NC}"
echo ""

# 1. 프로젝트 설정
echo -e "${YELLOW}1. GCP 프로젝트 설정 중...${NC}"
gcloud config set project $PROJECT_ID

# 2. 필요한 API 활성화
echo -e "${YELLOW}2. 필요한 API 활성화 중...${NC}"
gcloud services enable run.googleapis.com || echo "Cloud Run API 이미 활성화됨"
gcloud services enable cloudbuild.googleapis.com || echo "Cloud Build API 이미 활성화됨"

# 3. Docker 이미지 빌드 및 푸시
echo -e "${YELLOW}3. Docker 이미지 빌드 및 푸시 중...${NC}"
IMAGE_URL="gcr.io/$PROJECT_ID/$SERVICE_NAME"
echo "이미지 URL: $IMAGE_URL"

gcloud builds submit --tag $IMAGE_URL --timeout=20m

# 4. .env 파일에서 환경변수 읽기
echo -e "${YELLOW}4. 환경변수 설정 준비 중...${NC}"
if [ -f ".env" ]; then
    echo ".env 파일에서 환경변수를 읽어옵니다."
    
    # .env 파일에서 환경변수 추출 (주석, 빈 줄, Cloud Run 예약 변수 제외)
    ENV_VARS=$(grep -v '^#' .env | grep -v '^$' | grep -v '^PORT=' | sed 's/^//' | tr '\n' ',' | sed 's/,$//')
    
    # Redirect URI를 배포될 서비스 URL로 업데이트
    SERVICE_URL_PLACEHOLDER="https://cilantro-comment-detector-738575764165.asia-northeast3.run.app"
    # Cloud Run URL은 프로젝트 번호를 사용하므로 실제 배포된 URL 사용
    EXPECTED_SERVICE_URL="https://cilantro-comment-detector-738575764165.asia-northeast3.run.app"
    
    # CAFE24_REDIRECT_URI 업데이트
    ENV_VARS=$(echo "$ENV_VARS" | sed "s|CAFE24_REDIRECT_URI=[^,]*|CAFE24_REDIRECT_URI=$EXPECTED_SERVICE_URL/callback|")
    
    # 프로덕션용으로 일부 값 덮어쓰기 (중복 제거)
    ENV_VARS=$(echo "$ENV_VARS" | sed 's/DEBUG=[^,]*,//g' | sed 's/HOST=[^,]*,//g')
    ENV_VARS="$ENV_VARS,DEBUG=false,HOST=0.0.0.0"
    
    echo "설정될 환경변수들:"
    echo "$ENV_VARS" | tr ',' '\n' | sed 's/^/  - /'
else
    echo -e "${RED}⚠️  .env 파일을 찾을 수 없습니다. 기본값으로 배포합니다.${NC}"
    ENV_VARS="DEBUG=false,HOST=0.0.0.0,NOTIFICATION_ENABLED=true"
fi

# 5. Cloud Run에 배포
echo -e "${YELLOW}5. Cloud Run에 배포 중...${NC}"
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_URL \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --concurrency 80 \
  --max-instances 10 \
  --min-instances 0 \
  --port 8080 \
  --set-env-vars "$ENV_VARS"

# 6. 배포 완료 정보 출력
echo ""
echo -e "${GREEN}✅ 배포 완료!${NC}"

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
echo -e "${BLUE}🌐 서비스 URL: ${GREEN}$SERVICE_URL${NC}"

echo ""
echo -e "${YELLOW}📋 다음 단계:${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ 환경변수가 .env 파일에서 자동으로 설정되었습니다.${NC}"
    echo ""
    echo "1. 카페24 개발자 센터에서 Redirect URI 확인/업데이트:"
    echo "   $SERVICE_URL/callback"
    echo ""
    echo "2. 웹 대시보드 접속:"
    echo "   $SERVICE_URL"
    echo "   로그인: $(grep CAFE24_ID .env | cut -d'=' -f2) / $(grep CAFE24_PASSWORD .env | cut -d'=' -f2)"
else
    echo "1. 카페24 개발자 센터에서 Redirect URI 업데이트:"
    echo "   $SERVICE_URL/callback"
    echo ""
    echo "2. Cloud Run 콘솔에서 환경변수 설정:"
    echo "   https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/variables"
    echo ""
    echo "3. 필수 환경변수들:"
    echo "   - CAFE24_CLIENT_ID"
    echo "   - CAFE24_CLIENT_SECRET" 
    echo "   - CAFE24_ID"
    echo "   - CAFE24_PASSWORD"
    echo "   - CAFE24_REDIRECT_URI=$SERVICE_URL/callback"
    echo "   - SERVICE_KEY"
    echo "   - WEBHOOK_EVENT_KEY"
fi
echo ""
echo -e "${GREEN}🎉 배포가 성공적으로 완료되었습니다!${NC}"