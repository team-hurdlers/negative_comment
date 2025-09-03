# 카페24 API를 통한 리뷰 분석 시스템 사용법

## 개요

카페24 쇼핑몰의 실제 리뷰 데이터를 API를 통해 수집하고 감정 분석을 수행하는 시스템입니다. 기존의 웹 크롤링 방식과 함께 공식 API를 지원하여 더욱 안정적이고 정확한 데이터 수집이 가능합니다.

## 주요 기능

### 1. 카페24 OAuth 인증
- 카페24 개발자 센터에서 발급받은 앱 정보로 OAuth 2.0 인증
- Access Token 자동 갱신 및 관리
- 토큰 상태 실시간 모니터링

### 2. API 기반 리뷰 수집
- 리뷰 게시판 자동 탐지
- 최신 리뷰 실시간 수집
- 특정 상품 리뷰 조회
- 키워드 기반 리뷰 검색

### 3. 고도화된 감정 분석
- 다국어 지원 (한국어 특화)
- 신뢰도 기반 필터링
- 부정 리뷰 자동 분류
- 통계 및 트렌드 분석

## 시스템 구조

```
negative_comment/
├── auth/                    # OAuth 인증 모듈
│   ├── __init__.py
│   └── cafe24_oauth.py     # 카페24 OAuth 클라이언트
├── api/                     # API 관련 모듈
│   ├── __init__.py
│   ├── cafe24_reviews.py   # 카페24 리뷰 API
│   └── review_analyzer.py  # 리뷰 감정 분석기
├── utils/                   # 유틸리티 모듈
│   ├── __init__.py
│   ├── config_manager.py   # 설정 관리
│   └── notification.py     # 알림 관리
├── templates/              # HTML 템플릿
├── static/                # 정적 파일
├── app.py                 # Flask 메인 애플리케이션
├── config.json           # 설정 파일 (자동 생성)
└── known_reviews.json    # 모니터링 데이터
```

## 설치 및 설정

### 1. 필수 라이브러리 설치

```bash
pip install flask flask-cors transformers torch requests pandas
```

### 2. 카페24 개발자 앱 생성

1. [카페24 개발자 센터](https://developers.cafe24.com/) 접속
2. 로그인 후 "Apps" > "새 앱 만들기" 선택
3. 앱 정보 입력:
   - 앱 이름: `리뷰 분석 시스템`
   - Redirect URL: `http://localhost:5000/callback`
   - 권한: `mall.read_product`, `mall.read_category`, `mall.read_store`
4. Client ID와 Client Secret 메모

### 3. 환경변수 설정 (선택사항)

```bash
export CAFE24_CLIENT_ID="your_client_id"
export CAFE24_CLIENT_SECRET="your_client_secret"
export CAFE24_MALL_ID="cila01"
export CAFE24_REDIRECT_URI="http://localhost:5000/callback"
```

## 사용법

### 1. 서버 시작

```bash
python app.py
```

서버가 시작되면 다음과 같은 메시지를 볼 수 있습니다:

```
서버 시작 중...
=== 설정 상태 ===
카페24 Mall ID: cila01
카페24 Client ID: 미설정
카페24 Client Secret: 미설정
신뢰도 임계값: 0.7
분석 모델: nlptown/bert-base-multilingual-uncased-sentiment
모니터링 간격: 3600초
알림 활성화: True

⚠️  설정 오류:
  cafe24:
    - client_id가 설정되지 않았습니다.
    - client_secret이 설정되지 않았습니다.

다국어 감정 분석 모델 로드 완료
카페24 API 설정이 완료되지 않았습니다.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
```

### 2. API 설정

#### 웹 UI를 통한 설정

브라우저에서 `http://localhost:5000` 접속 후 설정 페이지에서 입력

#### API를 통한 설정

```bash
curl -X POST http://localhost:5000/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "mall_id": "cila01",
    "redirect_uri": "http://localhost:5000/callback"
  }'
```

### 3. OAuth 인증

#### Step 1: 인증 URL 생성

```bash
curl http://localhost:5000/auth/start
```

응답:
```json
{
  "auth_url": "https://cila01.cafe24api.com/api/v2/oauth/authorize?response_type=code&client_id=...",
  "state": "random_state_string",
  "message": "브라우저에서 인증 URL을 열어 인증을 진행해주세요."
}
```

#### Step 2: 브라우저에서 인증

1. 받은 `auth_url`을 브라우저에서 열기
2. 카페24 관리자 계정으로 로그인
3. 권한 승인
4. 자동으로 `/callback` 엔드포인트로 리다이렉트되어 토큰 발급 완료

### 4. 인증 상태 확인

```bash
curl http://localhost:5000/auth/status
```

응답 (인증 완료 시):
```json
{
  "configured": true,
  "authenticated": true,
  "token_valid": true,
  "status": "valid",
  "message": "유효한 토큰입니다.",
  "issued_at": "2025-01-20T10:30:00",
  "expires_at": "2025-01-20T12:30:00",
  "scopes": ["mall.read_product", "mall.read_category", "mall.read_store"]
}
```

## API 엔드포인트

### 인증 관련

| 엔드포인트 | 메소드 | 설명 |
|------------|--------|------|
| `/auth/setup` | GET/POST | API 설정 조회/설정 |
| `/auth/start` | GET | OAuth 인증 시작 |
| `/callback` | GET | OAuth 콜백 처리 |
| `/auth/status` | GET | 인증 상태 확인 |
| `/auth/revoke` | POST | 토큰 폐기 |

### 리뷰 API

| 엔드포인트 | 메소드 | 설명 |
|------------|--------|------|
| `/api/reviews/boards` | GET | 리뷰 게시판 목록 |
| `/api/reviews/latest` | GET | 최신 리뷰 조회 |
| `/api/reviews/product/<product_no>` | GET | 특정 상품 리뷰 |
| `/api/reviews/search` | GET | 리뷰 검색 |
| `/api/products` | GET | 상품 목록 조회 |

### 기존 기능

| 엔드포인트 | 메소드 | 설명 |
|------------|--------|------|
| `/crawl_and_analyze` | POST | URL 크롤링 및 분석 |
| `/start_monitoring` | POST | 모니터링 시작 |
| `/stop_monitoring` | POST | 모니터링 중지 |
| `/get_notifications` | GET | 알림 조회 |

## 사용 예시

### 1. 최신 리뷰 분석

```bash
# 최근 7일간의 리뷰 50개 분석
curl "http://localhost:5000/api/reviews/latest?days=7&limit=50"
```

응답:
```json
{
  "reviews": [
    {
      "board_no": 5,
      "board_name": "상품후기",
      "article_no": 123,
      "product_no": 456,
      "title": "정말 좋은 제품입니다",
      "content": "품질이 뛰어나고 배송도 빨랐어요...",
      "writer": "user123",
      "rating": 5,
      "created_date": "2025-01-20T10:00:00",
      "is_negative": false,
      "confidence": 0.95,
      "label": "긍정적",
      "score": 95.0
    }
  ],
  "statistics": {
    "total": 50,
    "negative": 5,
    "positive": 45,
    "negative_ratio": 10.0,
    "positive_ratio": 90.0,
    "average_confidence": 87.5
  },
  "negative_reviews": [
    // 부정 리뷰만 필터링된 결과
  ],
  "count": 50
}
```

### 2. 특정 상품 리뷰 분석

```bash
curl "http://localhost:5000/api/reviews/product/456?limit=100"
```

### 3. 키워드 검색

```bash
curl "http://localhost:5000/api/reviews/search?keyword=배송&limit=30"
```

### 4. 리뷰 게시판 목록 조회

```bash
curl http://localhost:5000/api/reviews/boards
```

응답:
```json
{
  "boards": [
    {
      "board_no": 5,
      "board_name": "상품후기",
      "board_type": "review"
    },
    {
      "board_no": 7,
      "board_name": "구매평",
      "board_type": "review"
    }
  ],
  "count": 2
}
```

## 고급 기능

### 1. 설정 관리

시스템 전체 설정 조회:
```bash
curl http://localhost:5000/config
```

### 2. 알림 시스템

```bash
# 대기 중인 알림 조회
curl http://localhost:5000/get_notifications

# 최근 알림 기록
curl "http://localhost:5000/notifications/recent?limit=20"

# 알림 통계
curl http://localhost:5000/notifications/statistics
```

### 3. 모니터링 기능

기존 URL 크롤링 모니터링과 병행 사용 가능:

```bash
# URL 모니터링 시작 (기존 기능)
curl -X POST http://localhost:5000/start_monitoring \
  -H "Content-Type: application/json" \
  -d '{"url": "https://shopping-url.com/product/123"}'

# 모니터링 상태 확인
curl http://localhost:5000/monitoring_status
```

## 문제 해결

### 1. 토큰 만료 시

토큰이 만료되면 자동으로 갱신을 시도합니다. 실패 시 재인증이 필요합니다:

```bash
# 토큰 상태 확인
curl http://localhost:5000/auth/status

# 수동 토큰 폐기 후 재인증
curl -X POST http://localhost:5000/auth/revoke
curl http://localhost:5000/auth/start
```

### 2. API 호출 제한

카페24 API는 "Leaky Bucket" 알고리즘을 사용합니다:
- 1초에 2회씩 호출 권한 회복
- 초당 10회 이상 호출 시 제한
- `X-Api-Call-Limit` 헤더로 사용량 확인 가능

### 3. 권한 오류

필요한 권한이 없는 경우 앱 설정에서 권한을 추가하고 재인증:
- `mall.read_product`: 상품 정보 조회
- `mall.read_category`: 카테고리 조회  
- `mall.read_store`: 스토어 정보 조회

### 4. 리뷰 게시판을 찾을 수 없는 경우

게시판 목록을 확인하고 수동으로 리뷰 게시판을 식별:

```bash
curl http://localhost:5000/api/reviews/boards
```

## 설정 파일

`config.json`이 자동 생성되며 다음과 같은 구조를 가집니다:

```json
{
  "cafe24": {
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "mall_id": "cila01",
    "redirect_uri": "http://localhost:5000/callback"
  },
  "analysis": {
    "confidence_threshold": 0.7,
    "model_name": "nlptown/bert-base-multilingual-uncased-sentiment",
    "fallback_model": "cardiffnlp/twitter-roberta-base-sentiment-latest"
  },
  "monitoring": {
    "check_interval": 3600,
    "max_reviews_per_check": 100,
    "notification_enabled": true
  },
  "app": {
    "debug": true,
    "port": 5000,
    "host": "0.0.0.0"
  }
}
```

## 로그 및 모니터링

- 시스템 로그는 콘솔에 실시간 출력
- 알림 기록은 `notification_history.json`에 저장
- 토큰 정보는 `cafe24_tokens_{mall_id}.json`에 저장
- 모니터링 데이터는 `known_reviews.json`에 저장

## 보안 고려사항

1. **Client Secret 보안**: 환경변수 사용 권장
2. ** 사용**: 프로덕션에서는 HTTPS 필수
3. **Session Secret**: `SECRET_KEY` 환경변수 설정
4. **토큰 저장**: 민감한 정보를 안전한 위치에 저장

## 성능 최적화

1. **API 호출 최적화**: rate limiting 준수
2. **배치 처리**: 대용량 데이터 처리 시 청크 단위로 분할
3. **캐싱**: 자주 조회하는 데이터는 캐싱 활용
4. **비동기 처리**: 무거운 작업은 백그라운드에서 처리

## 향후 개발 계획

- [ ] 웹 대시보드 UI 개선
- [ ] 실시간 알림 (WebSocket)
- [ ] 데이터베이스 연동
- [ ] 상품별 리뷰 트렌드 분석
- [ ] 경쟁업체 비교 분석
- [ ] 자동 응답 기능
- [ ] 리포트 자동 생성