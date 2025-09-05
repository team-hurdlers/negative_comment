# 카페24 API 리뷰 분석 시스템 - 빠른 시작

## 🚀 30초 빠른 설정

### 1. 서버 실행
```bash
python app.py
```

### 2. 카페24 개발자 센터에서 앱 생성
- [카페24 개발자센터](https://developers.cafe24.com/) → 로그인 → "새 앱 만들기"
- Redirect URL: `http://localhost:5001/callback`
- Client ID, Client Secret 복사

### 3. API 설정
브라우저에서 `http://localhost:5001` → 설정 페이지에서 입력

또는 cURL:
```bash
curl -X POST http://localhost:5001/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "발급받은_클라이언트_ID",
    "client_secret": "발급받은_클라이언트_시크릿",
    "mall_id": "cila01"
  }'
```

### 4. OAuth 인증
```bash
# 인증 URL 생성
curl http://localhost:5000/auth/start

# 응답에서 auth_url을 브라우저에서 열고 승인
```

### 5. 리뷰 분석 시작! 🎉

```bash
# 최근 리뷰 분석
curl "http://localhost:5000/api/reviews/latest?limit=10"

# 특정 상품 리뷰 분석  
curl "http://localhost:5000/api/reviews/product/상품번호"

# 키워드 검색
curl "http://localhost:5000/api/reviews/search?keyword=배송"
```

---

## 📋 주요 API 엔드포인트

### ✅ 인증 완료 후 사용 가능

| API | 설명 | 예시 |
|-----|------|------|
| `GET /api/reviews/latest` | 최신 리뷰 | `?days=7&limit=50` |
| `GET /api/reviews/product/<번호>` | 상품별 리뷰 | `/api/reviews/product/123` |
| `GET /api/reviews/search` | 리뷰 검색 | `?keyword=품질&limit=30` |
| `GET /api/reviews/boards` | 리뷰 게시판 목록 | - |
| `GET /api/products` | 상품 목록 | `?limit=100` |

### 🔧 설정 및 상태

| API | 설명 |
|-----|------|
| `GET /auth/status` | 인증 상태 확인 |
| `GET /config` | 현재 설정 조회 |
| `GET /get_notifications` | 알림 조회 |

---

## 📊 응답 예시

### 최신 리뷰 분석 결과
```json
{
  "reviews": [
    {
      "title": "정말 만족합니다",
      "content": "품질 좋고 배송 빨라요",
      "is_negative": false,
      "confidence": 0.95,
      "score": 95.0,
      "product_no": 123
    }
  ],
  "statistics": {
    "total": 50,
    "negative": 3,
    "positive": 47,
    "negative_ratio": 6.0
  },
  "negative_reviews": [
    // 부정 리뷰만 필터링된 결과
  ]
}
```

---

## ⚡ 빠른 문제 해결

### 인증 오류
```bash
# 상태 확인
curl http://localhost:5000/auth/status

# 재인증
curl http://localhost:5000/auth/start
```

### 리뷰를 찾을 수 없음
```bash
# 게시판 목록 확인
curl http://localhost:5000/api/reviews/boards
```

### 토큰 만료
자동으로 갱신됩니다. 실패 시 재인증하세요.

---

## 🎯 주요 사용 시나리오

### 1️⃣ 일일 리뷰 모니터링
```bash
# 오늘의 새 리뷰 확인
curl "http://localhost:5000/api/reviews/latest?days=1&limit=100"
```

### 2️⃣ 특정 상품 문제 파악
```bash
# 상품별 부정 리뷰 분석
curl "http://localhost:5000/api/reviews/product/123?limit=50"
```

### 3️⃣ 고객 불만 키워드 추적
```bash
# 배송 관련 리뷰 검색
curl "http://localhost:5000/api/reviews/search?keyword=배송지연"
```

### 4️⃣ 전체 만족도 트렌드
```bash
# 최근 1주일 리뷰 분석
curl "http://localhost:5000/api/reviews/latest?days=7&limit=200"
```

---

## 🔗 추가 자료

- [상세 사용법 가이드](./CAFE24_API_GUIDE.md)
- [카페24 API 문서](https://developers.cafe24.com/docs/ko/api/)
- [OAuth 2.0 인증 플로우](https://developers.cafe24.com/docs/ko/api/admin/#oauth)

---

**문제가 있으시면 GitHub Issues에 등록해주세요!** 🙋‍♂️