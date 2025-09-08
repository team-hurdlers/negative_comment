import json
import os
import numpy as np
from datetime import datetime
from app.infrastructure.external.openai.review_analyzer import ReviewAnalyzer

class ReviewService:
    def __init__(self, notification_manager=None):
        self.notification_manager = notification_manager
        
        # 모니터링 관련 변수
        self.monitoring_active = False
        self.monitoring_thread = None
        self.known_reviews = set()  # 이미 확인한 리뷰들 저장 (API용)
        self.pending_notifications = []  # 대기 중인 알림들
        self.DATA_FILE = 'known_reviews.json'
        
        # 카페24 API 리뷰 캐시 시스템
        self.REVIEW_CACHE_FILE = 'review_cache.json'
        self.cached_reviews = []  # 최신 리뷰 10개 캐시
        
        # 모델 관련
        self.sentiment_analyzer = None
        self.review_analyzer = None
        
    def load_model(self):
        """모델 로드"""
        try:
            # 1. 기존 경량 모델 로드 (백업용)
            import joblib
            model_path = 'final_svm_sentiment_model.pkl'
            print(f"경량 감정 분석 모델 로드 시작: {model_path}")
            
            self.sentiment_analyzer = joblib.load(model_path)
            print(f"경량 감정 분석 모델 로드 완료: {model_path}")
            print(f"모델 타입: {type(self.sentiment_analyzer)}")
            
            # 2. 새로운 ReviewAnalyzer 초기화 (GPT + pkl 하이브리드)
            print("🚀 ReviewAnalyzer 초기화 시작...")
            self.review_analyzer = ReviewAnalyzer()
            print("✅ ReviewAnalyzer 초기화 완료!")
            
        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")
            self.sentiment_analyzer = None
            self.review_analyzer = None

    def load_known_reviews(self):
        """저장된 기존 리뷰 목록 로드"""
        try:
            if os.path.exists(self.DATA_FILE):
                with open(self.DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.known_reviews = set(data.get('reviews', []))
                    print(f"기존 리뷰 {len(self.known_reviews)}개 로드 완료")
            else:
                self.known_reviews = set()
                print("새로운 모니터링 시작")
        except Exception as e:
            print(f"기존 리뷰 로드 오류: {e}")
            self.known_reviews = set()

    def save_known_reviews(self):
        """현재 리뷰 목록 저장 (API용)"""
        try:
            with open(self.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'reviews': list(self.known_reviews),
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"리뷰 저장 오류: {e}")

    def load_review_cache(self):
        """저장된 리뷰 캐시 로드"""
        try:
            if os.path.exists(self.REVIEW_CACHE_FILE):
                with open(self.REVIEW_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.cached_reviews = data.get('reviews', [])
                    print(f"리뷰 캐시 {len(self.cached_reviews)}개 로드 완료")
            else:
                self.cached_reviews = []
                print("새로운 리뷰 캐시 시작")
        except Exception as e:
            print(f"리뷰 캐시 로드 오류: {e}")
            self.cached_reviews = []

    def save_review_cache(self):
        """현재 리뷰 캐시 저장"""
        try:
            with open(self.REVIEW_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'reviews': self.cached_reviews,
                    'last_updated': datetime.now().isoformat(),
                    'count': len(self.cached_reviews)
                }, f, ensure_ascii=False, indent=2)
            print(f"리뷰 캐시 {len(self.cached_reviews)}개 저장 완료")
        except Exception as e:
            print(f"리뷰 캐시 저장 오류: {e}")

    def initialize_review_cache(self, review_api):
        """리뷰 캐시 초기화 - 최신 리뷰 10개로 캐시 설정"""
        if not review_api:
            print("❌ Review API가 초기화되지 않았습니다.")
            return False
        
        try:
            print("🔄 리뷰 캐시 초기화 중...")
            latest_reviews = review_api.get_latest_reviews(limit=10)
            
            if latest_reviews:
                self.cached_reviews = latest_reviews
                self.save_review_cache()
                print(f"✅ 리뷰 캐시 초기화 완료: {len(self.cached_reviews)}개")
                return True
            else:
                print("⚠️ 초기화할 리뷰가 없습니다.")
                return False
        except Exception as e:
            print(f"❌ 리뷰 캐시 초기화 실패: {e}")
            return False

    def find_new_reviews(self, review_api):
        """현재 최신 리뷰와 캐시 비교해서 신규 리뷰 찾기"""
        if not review_api:
            return []
        
        try:
            # 현재 최신 리뷰 10개 조회
            current_reviews = review_api.get_latest_reviews(limit=10)
            if not current_reviews:
                return []
            
            # 웹훅 기반 스마트 처리
            if not self.cached_reviews:
                # 캐시가 비어있으면 (컨테이너 재시작 후)
                # 웹훅이 왔다는 건 신규 리뷰가 있다는 뜻이므로 최신 1개만 처리
                new_reviews = current_reviews[:1]
                print(f"🔄 컨테이너 재시작 후 웹훅 수신 - 최신 리뷰 1개 처리")
            else:
                # 캐시가 있으면 기존 로직으로 중복 체크
                cached_article_nos = {str(review.get('article_no', '')) for review in self.cached_reviews}
                
                new_reviews = []
                for review in current_reviews:
                    article_no = str(review.get('article_no', ''))
                    if article_no and article_no not in cached_article_nos:
                        new_reviews.append(review)
            
            if new_reviews:
                print(f"🆕 신규 리뷰 {len(new_reviews)}개 발견!")
                
                # 캐시 업데이트: 신규 리뷰 추가하고 최신 10개만 유지
                all_reviews = new_reviews + self.cached_reviews
                self.cached_reviews = all_reviews[:10]  # 최신 10개만 유지
                self.save_review_cache()
                
            return new_reviews
            
        except Exception as e:
            print(f"신규 리뷰 찾기 오류: {e}")
            return []

    def analyze_review(self, review_text, rating=None):
        """단일 리뷰 감정 분석 (GPT+pkl 하이브리드)"""
        try:
            # 모델 로드
            if self.review_analyzer is None and self.sentiment_analyzer is None:
                self.load_model()
            
            # ReviewAnalyzer 우선 사용 (GPT 2차 분석 포함)
            if self.review_analyzer is not None:
                return self.review_analyzer.analyze_single_review(review_text, rating)
            
            # 폴백: 기존 pkl 모델 사용
            if self.sentiment_analyzer is None:
                return {'is_negative': False, 'confidence': 0, 'error': '모델 로드 실패'}
            
            # scikit-learn 파이프라인 모델 사용
            try:
                # TfidfVectorizer + LogisticRegression 파이프라인인 경우
                if hasattr(self.sentiment_analyzer, 'predict_proba') and hasattr(self.sentiment_analyzer, 'predict'):
                    
                    # 예측 수행
                    prediction = self.sentiment_analyzer.predict([review_text])
                    prediction_proba = self.sentiment_analyzer.predict_proba([review_text])
                    
                    predicted_class = prediction[0]
                    probabilities = prediction_proba[0]
                    
                    # 클래스 라벨 확인 (모델 학습 시 사용된 라벨)
                    classes = self.sentiment_analyzer.classes_ if hasattr(self.sentiment_analyzer, 'classes_') else ['negative', 'positive']
                    
                    print(f"🔍 모델 클래스: {classes}")
                    print(f"🔍 예측 결과: {predicted_class}")
                    print(f"🔍 확률: {probabilities}")
                    
                    # 알림 필요성 판단: negative와 neutral 모두 알림 대상
                    if predicted_class == 'negative':
                        is_negative = True
                        confidence = probabilities[list(classes).index('negative')] if 'negative' in classes else probabilities[0]
                    elif predicted_class == 'neutral':
                        is_negative = True  # 보통 리뷰도 알림 대상
                        confidence = probabilities[list(classes).index('neutral')] if 'neutral' in classes else probabilities[1]
                    elif predicted_class == 'positive':
                        is_negative = False
                        confidence = probabilities[list(classes).index('positive')] if 'positive' in classes else probabilities[2]
                    else:
                        # 알 수 없는 라벨의 경우
                        max_prob_idx = np.argmax(probabilities)
                        confidence = probabilities[max_prob_idx]
                        is_negative = max_prob_idx != list(classes).index('positive') if 'positive' in classes else True
                    
                    print(f"🔍 경량 모델 결과: 예측={predicted_class}, 신뢰도={confidence:.3f}")
                    
                elif hasattr(self.sentiment_analyzer, 'predict'):
                    # predict만 있는 경우
                    prediction = self.sentiment_analyzer.predict([review_text])
                    predicted_class = prediction[0]
                    
                    is_negative = predicted_class == 'negative' or predicted_class == 'neutral'
                    confidence = 0.8  # 기본값
                    
                    print(f"🔍 경량 모델 결과 (predict only): 예측={predicted_class}")
                    
                else:
                    # 지원하지 않는 모델 형태
                    return {'is_negative': False, 'confidence': 0, 'error': '지원하지 않는 모델 형태입니다'}
                    
            except Exception as model_error:
                print(f"모델 예측 오류: {model_error}")
                import traceback
                traceback.print_exc()
                return {'is_negative': False, 'confidence': 0, 'error': f'모델 예측 실패: {str(model_error)}'}
            
            # 라벨 설정
            if 'predicted_class' in locals() and predicted_class == 'negative':
                korean_label = '부정적'
            elif 'predicted_class' in locals() and predicted_class == 'neutral':
                korean_label = '보통'
            elif 'predicted_class' in locals() and predicted_class == 'positive':
                korean_label = '긍정적'
            else:
                korean_label = '부정적' if is_negative else '긍정적'
            
            print(f"🎯 최종 분류: {korean_label} (is_negative={is_negative}, confidence={confidence:.3f})")
            
            return {
                'is_negative': is_negative,
                'confidence': confidence,
                'label': korean_label,
                'score': round(confidence * 100, 2)
            }
            
        except Exception as e:
            print(f"❌ 리뷰 분석 오류: {e}")
            import traceback
            traceback.print_exc()
            return {'is_negative': False, 'confidence': 0, 'error': str(e)}

    def send_notification(self, new_reviews, negative_reviews):
        """신규 리뷰 알림 (콘솔 출력 + 브라우저 알림 준비)"""
        print("\n" + "="*50)
        print("🚨 신규 리뷰 감지!")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"신규 리뷰: {len(new_reviews)}개")
        print(f"부정 리뷰: {len(negative_reviews)}개")
        print("="*50)
        
        # NotificationManager를 사용한 알림 추가
        if self.notification_manager:
            self.notification_manager.add_review_notification(new_reviews, negative_reviews)
        
        # 기존 pending_notifications도 유지 (하위 호환성)
        if new_reviews:
            if negative_reviews:
                # 부정 리뷰가 있으면 우선 알림
                title = f"⚠️ 부정 리뷰 {len(negative_reviews)}개 발견!"
                body = f"신규 리뷰 총 {len(new_reviews)}개 중 부정 리뷰: {negative_reviews[0]['text'][:50]}..."
                notification_type = "negative"
            else:
                # 일반 신규 리뷰 알림
                title = f"📝 신규 리뷰 {len(new_reviews)}개 발견"
                body = f"최신 리뷰: {new_reviews[0]['text'][:50]}..."
                notification_type = "new"
            
            # 알림 큐에 추가
            self.pending_notifications.append({
                'title': title,
                'body': body,
                'type': notification_type,
                'timestamp': datetime.now().isoformat(),
                'new_count': len(new_reviews),
                'negative_count': len(negative_reviews)
            })
        
        if negative_reviews:
            print("⚠️ 부정적인 신규 리뷰:")
            for i, review in enumerate(negative_reviews[:3], 1):  # 최대 3개만 표시
                print(f"{i}. {review['text'][:100]}...")
                print(f"   신뢰도: {review['score']}%")
        
        if new_reviews:
            print("📝 모든 신규 리뷰:")
            for i, review in enumerate(new_reviews[:5], 1):  # 최대 5개만 표시
                emoji = "⚠️" if review.get('is_negative', False) else "✅"
                print(f"{i}. {emoji} {review['text'][:80]}...")
        
        print("="*50 + "\n")
    
    def analyze_reviews_batch(self, reviews):
        """리뷰 목록 일괄 분석 (GPT+pkl 하이브리드)"""
        # ReviewAnalyzer가 없으면 기존 방식으로 폴백
        if self.review_analyzer is None:
            analyzed_reviews = []
            for review in reviews:
                review_text = review.get('content', '') or review.get('text', '') or review.get('title', '')
                rating = review.get('rating', 0)
                analysis_result = self.analyze_review(review_text, rating)
                analyzed_review = review.copy()
                analyzed_review.update(analysis_result)
                analyzed_reviews.append(analyzed_review)
            return analyzed_reviews
        
        # ReviewAnalyzer 사용 (GPT 2차 분석 포함)
        return self.review_analyzer.analyze_reviews_batch(reviews)

    def get_review_statistics(self, reviews):
        """리뷰 통계 정보 (경량 버전)"""
        if not reviews:
            return {
                'total': 0,
                'negative': 0,
                'positive': 0,
                'negative_ratio': 0,
                'positive_ratio': 0,
                'average_confidence': 0
            }
        
        total = len(reviews)
        negative_count = sum(1 for r in reviews if r.get('is_negative', False))
        positive_count = total - negative_count
        
        # 평균 신뢰도 계산
        total_confidence = sum(r.get('confidence', 0) for r in reviews)
        average_confidence = total_confidence / total if total > 0 else 0
        
        return {
            'total': total,
            'negative': negative_count,
            'positive': positive_count,
            'negative_ratio': round((negative_count / total) * 100, 2),
            'positive_ratio': round((positive_count / total) * 100, 2),
            'average_confidence': round(average_confidence * 100, 2)
        }

    def get_negative_reviews(self, reviews, confidence_threshold=0.7):
        """부정 리뷰만 필터링 (경량 버전)"""
        negative_reviews = []
        
        for review in reviews:
            if (review.get('is_negative', False) and 
                review.get('confidence', 0) >= confidence_threshold):
                negative_reviews.append(review)
        
        # 신뢰도순으로 정렬
        negative_reviews.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        return negative_reviews