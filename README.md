# 부정댓글 탐지기

한국어 텍스트의 감성을 분석하여 부정적/긍정적 댓글을 탐지하는 웹 애플리케이션입니다.

## 주요 기능

- **단일 텍스트 분석**: 하나의 텍스트를 입력하여 감성 분석
- **다중 텍스트 분석**: 여러 텍스트를 한 번에 분석하고 통계 제공
- **🛒 쇼핑몰 URL 분석**: 쇼핑몰 제품 URL 입력 시 자동으로 리뷰 크롤링 및 부정댓글 탐지
  - 지원 사이트: 쿠팡, 네이버 쇼핑, 11번가, G마켓, 옥션, 인터파크 등
  - 제품별 리뷰 자동 수집 및 분석
  - 부정/긍정 리뷰 자동 분류 및 통계
- **실시간 분석**: 한국어 BERT 모델을 사용한 정확한 감성 분석
- **직관적인 UI**: 분석 결과를 시각적으로 표시

## 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/team-hurdlers/negative_comment.git
cd negative_comment
```

### 2. 가상환경 생성 및 활성화
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. Chrome 드라이버 설치 (URL 크롤링 기능 사용 시)
Selenium을 사용하는 일부 사이트 크롤링을 위해 Chrome 드라이버가 필요합니다:
- Chrome 브라우저가 설치되어 있어야 합니다
- ChromeDriver를 다운로드: https://chromedriver.chromium.org/
- 시스템 PATH에 추가하거나 프로젝트 폴더에 위치

## 실행 방법

### 서버 시작
```bash
python app.py
```

서버가 시작되면 브라우저에서 http://localhost:5000 으로 접속합니다.

### API 테스트
```bash
python test_api.py
```

## API 엔드포인트

### POST /analyze
단일 텍스트 분석

**요청:**
```json
{
    "text": "분석할 텍스트"
}
```

**응답:**
```json
{
    "text": "분석할 텍스트",
    "is_negative": false,
    "confidence": 0.95,
    "label": "긍정적",
    "score": 95.0
}
```

### POST /batch_analyze
다중 텍스트 일괄 분석

**요청:**
```json
{
    "texts": ["텍스트1", "텍스트2", "텍스트3"]
}
```

**응답:**
```json
{
    "results": [
        {
            "text": "텍스트1",
            "is_negative": false,
            "confidence": 0.95,
            "label": "긍정적",
            "score": 95.0
        }
    ],
    "summary": {
        "total": 3,
        "negative": 1,
        "positive": 2,
        "negative_ratio": 33.33
    }
}
```

### POST /crawl_and_analyze
쇼핑몰 URL 리뷰 크롤링 및 분석

**요청:**
```json
{
    "url": "https://www.coupang.com/vp/products/..."
}
```

**응답:**
```json
{
    "product": {
        "title": "제품명",
        "price": "가격",
        "url": "제품 URL"
    },
    "reviews": [분석된 리뷰 배열],
    "summary": {
        "total": 50,
        "negative": 10,
        "positive": 40,
        "negative_ratio": 20.0
    },
    "top_negative": [상위 5개 부정 리뷰],
    "top_positive": [상위 5개 긍정 리뷰]
}
```

## 기술 스택

- **Backend**: Flask (Python)
- **ML Model**: Hugging Face Transformers (KcBERT)
- **Frontend**: HTML, CSS, JavaScript
- **Web Crawling**: BeautifulSoup4, Selenium
- **모델**: beomi/kcbert-base (한국어 감성 분석)

## 프로젝트 구조

```
negative_comment/
├── app.py              # Flask 서버
├── crawler.py          # 웹 크롤링 모듈
├── templates/
│   └── index.html      # 웹 인터페이스
├── test_api.py         # API 테스트 스크립트
├── requirements.txt    # 패키지 의존성
└── README.md          # 프로젝트 문서
```

## 주의사항

- 첫 실행 시 모델 다운로드로 인해 시간이 걸릴 수 있습니다.
- Python 3.8 이상 권장
- GPU가 없어도 CPU에서 실행 가능합니다.

## 라이선스

MIT License