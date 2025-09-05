from flask import Flask, request, jsonify, render_template, redirect, session, url_for
from flask_cors import CORS
from auth.cafe24_oauth import Cafe24OAuth
from api import Cafe24ReviewAPI
from utils import NotificationManager
import warnings
import threading
import time
import json
import os
import requests
import numpy as np
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from functools import wraps

# Settings 클래스 import
from config.settings import settings
warnings.filterwarnings('ignore')

app = Flask(__name__)
CORS(app)

# Flask 세션용 비밀키 설정 (Gunicorn에서도 동작하도록)
app.secret_key = settings.SERVICE_KEY or 'dev-secret-key-fallback'

# 설정 및 관리자 초기화
notification_manager = NotificationManager()

# OAuth 클라이언트와 Review API를 위한 전역 변수 (나중에 초기화됨)
oauth_client = None
review_api = None

# 채널톡 웹훅 설정
WEBHOOK_EVENT_KEY = settings.WEBHOOK_EVENT_KEY
WEBHOOK_ENABLED = True

# OAuth 클라이언트 lazy initialization 함수
def get_or_create_oauth_client():
    """OAuth 클라이언트를 lazy하게 초기화하여 반환"""
    global oauth_client
    
    # 이미 초기화된 경우 기존 클라이언트 반환
    if oauth_client is not None:
        return oauth_client
    
    # 환경변수 확인
    if not settings.cafe24_client_id or not settings.cafe24_client_secret:
        missing = []
        if not settings.cafe24_client_id:
            missing.append("CAFE24_CLIENT_ID")
        if not settings.cafe24_client_secret:
            missing.append("CAFE24_CLIENT_SECRET")
        print(f"❌ OAuth 설정이 완료되지 않았습니다. 누락: {', '.join(missing)}")
        return None
    
    # OAuth 클라이언트 생성
    try:
        oauth_client = Cafe24OAuth(
            client_id=settings.cafe24_client_id,
            client_secret=settings.cafe24_client_secret,
            mall_id=settings.cafe24_id,
            redirect_uri=settings.cafe24_redirect_uri
        )
        print(f"✅ OAuth 클라이언트 lazy 초기화 완료")
        print(f"   - Mall ID: {settings.cafe24_id}")
        print(f"   - Client ID: {settings.cafe24_client_id}")
        print(f"   - Redirect URI: {settings.cafe24_redirect_uri}")
        return oauth_client
        
    except Exception as e:
        print(f"❌ OAuth 클라이언트 초기화 실패: {e}")
        return None

def init_oauth_client():
    """기존 코드 호환성을 위한 wrapper 함수"""
    return get_or_create_oauth_client()



# 경량 분석 함수들
def analyze_reviews_batch(reviews):
    """리뷰 목록 일괄 분석 (경량 버전)"""
    analyzed_reviews = []
    for review in reviews:
        # 리뷰 텍스트 추출
        review_text = review.get('content', '') or review.get('text', '') or review.get('title', '')
        
        # 감정 분석 수행
        analysis_result = analyze_review(review_text)
        
        # 원본 리뷰 데이터와 분석 결과 병합
        analyzed_review = review.copy()
        analyzed_review.update(analysis_result)
        analyzed_reviews.append(analyzed_review)
    
    return analyzed_reviews

def get_review_statistics(reviews):
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

def get_negative_reviews(reviews, confidence_threshold=0.7):
    """부정 리뷰만 필터링 (경량 버전)"""
    negative_reviews = []
    
    for review in reviews:
        if (review.get('is_negative', False) and 
            review.get('confidence', 0) >= confidence_threshold):
            negative_reviews.append(review)
    
    # 신뢰도순으로 정렬
    negative_reviews.sort(key=lambda x: x.get('confidence', 0), reverse=True)
    
    return negative_reviews

sentiment_analyzer = None

# 상품명 캐시 (성능 향상을 위해)
product_cache = {}

# 인증 관련 유틸리티 함수들
def login_required(f):
    """로그인이 필요한 엔드포인트를 보호하는 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': '로그인이 필요합니다.', 'login_required': True}), 401
        return f(*args, **kwargs)
    return decorated_function

def cafe24_auth_required(f):
    """카페24 API 인증이 필요한 엔드포인트를 보호하는 데코레이터 (웹훅용 - 로그인 불필요)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def full_auth_required(f):
    """사용자 로그인 + 카페24 API 인증 둘 다 필요한 엔드포인트 (프론트엔드 API용)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 먼저 사용자 로그인 체크
        if 'user' not in session:
            return jsonify({'error': '로그인이 필요합니다.', 'login_required': True}), 401
        
        # 그 다음 카페24 API 토큰 체크
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.', 'cafe24_auth_required': True}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def verify_credentials(username, password):
    """사용자 인증 확인"""
    return username == settings.cafe24_id and password == settings.cafe24_password

def verify_webhook_event_key(event_key):
    """채널톡 웹훅 이벤트 키 검증"""
    try:
        if not WEBHOOK_EVENT_KEY:
            print("WEBHOOK_EVENT_KEY가 설정되지 않았습니다.")
            return False
        return event_key == WEBHOOK_EVENT_KEY
    except Exception as e:
        print(f"웹훅 이벤트 키 검증 오류: {e}")
        return False

def process_cafe24_webhook(webhook_data):
    """카페24 웹훅 데이터 처리 (게시판 글 등록)"""
    try:
        event_no = webhook_data.get('event_no')
        event_type = f"event_{event_no}" if event_no else webhook_data.get('event_type')
        print(f"🔍 카페24 웹훅 처리 시작 - 이벤트 번호: {event_no}, 타입: {event_type}")
        
        # 게시판 글 등록 이벤트 처리 (event_no: 90033)
        if event_no == 90033 or event_type in ['board.created', 'board_created']:
            print(f"📝 카페24 게시판 글 등록 이벤트 수신 - 신규 리뷰 확인 시작!")
            
            # 웹훅을 트리거로 사용해서 기존 리뷰 조회 로직 실행
            if review_api:
                print("🔍 웹훅 트리거로 인한 신규 리뷰 조회 시작...")
                trigger_review_collection()
                return True
            else:
                print("❌ Review API가 초기화되지 않았습니다.")
                return False
        else:
            print(f"⏭️ 처리 대상이 아닌 이벤트: {event_type}")
        
        return False
        
    except Exception as e:
        print(f"❌ 카페24 웹훅 처리 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def extract_content_from_cafe24_webhook(webhook_data):
    """카페24 웹훅 데이터에서 게시판 글 내용 추출"""
    try:
        # 카페24 웹훅 데이터 구조에 맞게 추출
        resource = webhook_data.get('resource', {})
        
        return {
            'text': resource.get('content', '') or resource.get('title', ''),
            'author': resource.get('writer', {}).get('name') if isinstance(resource.get('writer'), dict) else resource.get('writer', 'Unknown'),
            'board_no': resource.get('board_no'),
            'article_no': resource.get('article_no'),
            'created_date': resource.get('created_date'),
            'source': 'cafe24_webhook'
        }
        
    except Exception as e:
        print(f"카페24 웹훅 데이터 추출 오류: {e}")
        return None

def process_channel_talk_webhook(webhook_data):
    """채널톡 웹훅 데이터 처리"""
    try:
        event_type = webhook_data.get('eventType')
        print(f"🔍 웹훅 처리 시작 - 이벤트 타입: {event_type}")
        
        # 리뷰 관련 이벤트만 처리
        if event_type in ['review.created', 'review.updated', 'message.created']:
            print(f"📝 채널톡 웹훅 이벤트 수신: {event_type}")
            
            # 웹훅 데이터에서 리뷰/메시지 내용 추출
            content = extract_content_from_webhook(webhook_data)
            print(f"📄 추출된 내용: {content}")
            
            if content:
                # 감정 분석 수행
                analysis_result = analyze_review(content['text'])
                print(f"🤖 감정 분석 결과: {analysis_result}")
                
                if analysis_result.get('is_negative', False):
                    print("🚨 부정 리뷰 감지! 알림 발송 시작...")
                    # 부정 리뷰 감지 - 알림 발송
                    send_negative_review_alert(content, analysis_result)
                    
                    # 즉시 카페24 API로 최신 리뷰도 확인
                    if review_api:
                        trigger_review_collection()
                else:
                    print("😊 긍정적/중성적 리뷰로 분류됨 - 알림 없음")
                
                return True
            else:
                print("❌ 내용 추출 실패")
        else:
            print(f"⏭️ 처리 대상이 아닌 이벤트: {event_type}")
        
        return False
        
    except Exception as e:
        print(f"❌ 채널톡 웹훅 처리 오류: {e}")
        return False

def extract_content_from_webhook(webhook_data):
    """웹훅 데이터에서 리뷰/메시지 내용 추출"""
    try:
        event_type = webhook_data.get('eventType')
        data = webhook_data.get('data', {})
        
        # 이벤트 타입별 데이터 구조가 다름
        if event_type == 'review.created':
            return {
                'text': data.get('content', ''),
                'author': data.get('author', {}).get('name', 'Unknown'),
                'rating': data.get('rating'),
                'product': data.get('product', {}),
                'created_at': data.get('createdAt'),
                'source': 'channel_talk_review'
            }
        elif event_type == 'message.created':
            return {
                'text': data.get('message', ''),
                'author': data.get('user', {}).get('name', 'Unknown'),
                'channel': data.get('channel', {}),
                'created_at': data.get('createdAt'),
                'source': 'channel_talk_message'
            }
        
        return None
        
    except Exception as e:
        print(f"웹훅 데이터 추출 오류: {e}")
        return None

def send_negative_review_alert(content, analysis_result):
    """부정 리뷰 감지 시 즉시 알림 발송"""
    try:
        alert_data = {
            'type': 'negative_review_detected',
            'content': content['text'][:200],
            'author': content.get('author', 'Unknown'),
            'score': analysis_result.get('score', 0),
            'confidence': analysis_result.get('confidence', 0),
            'source': content.get('source', 'webhook'),
            'detected_at': datetime.now().isoformat()
        }
        
        print(f"📡 알림 데이터 생성: {alert_data}")
        
        # 알림 매니저에 긴급 알림 추가
        notification_result = notification_manager.add_monitoring_notification(
            'urgent_negative_review',
            f"🚨 긴급! 부정 리뷰 감지: {content['text'][:50]}...",
            alert_data
        )
        
        print(f"📢 알림 매니저 결과: {notification_result}")
        print(f"✅ 부정 리뷰 긴급 알림 발송 완료: {content['text'][:50]}...")
        
    except Exception as e:
        print(f"❌ 부정 리뷰 알림 발송 오류: {e}")
        import traceback
        traceback.print_exc()

def trigger_review_collection():
    """웹훅 트리거 시 신규 리뷰만 수집하고 분석"""
    try:
        if not review_api:
            print("❌ Review API가 없습니다.")
            return False
            
        print("🔍 웹훅 트리거로 인한 신규 리뷰 수집 시작...")
        
        # 신규 리뷰만 찾기
        new_reviews = find_new_reviews()
        
        if new_reviews:
            print(f"📝 신규 리뷰 {len(new_reviews)}개에 대해 감정 분석 시작...")
            
            # 신규 리뷰들만 감정 분석 수행
            analyzed_reviews = analyze_reviews_batch(new_reviews)
            negative_reviews = [r for r in analyzed_reviews if r.get('is_negative', False)]
            
            if negative_reviews:
                print(f"🚨 신규 부정 리뷰 {len(negative_reviews)}개 발견!")
                
                # 카카오톡 알림 전송
                notification_manager.send_review_alert_to_kakao(new_reviews, negative_reviews)
                
                for review in negative_reviews:
                    content_text = review.get('content', '') or review.get('title', '')
                    notification_manager.add_monitoring_notification(
                        'new_negative_review',
                        f"🚨 신규 부정 리뷰 감지: {content_text[:50]}...",
                        {
                            'type': 'cafe24_webhook',
                            'review': review,
                            'triggered_by': 'webhook',
                            'analysis': {
                                'is_negative': review.get('is_negative'),
                                'confidence': review.get('confidence'),
                                'score': review.get('score')
                            }
                        }
                    )
            else:
                print(f"😊 신규 리뷰 {len(new_reviews)}개는 모두 긍정적/중성적입니다.")
                
                # 일반 신규 리뷰도 알림 전송 (설정에 따라)
                if settings.notification_enabled:
                    notification_manager.send_review_alert_to_kakao(new_reviews, [])
                
            print(f"✅ 신규 리뷰 분석 완료: 총 {len(new_reviews)}개, 부정 {len(negative_reviews)}개")
        else:
            print("📝 신규 리뷰가 없습니다.")
        
        return True
        
    except Exception as e:
        print(f"❌ 웹훅 트리거 리뷰 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def enrich_reviews_with_product_names(reviews):
    """리뷰에 상품명 정보를 추가"""
    global product_cache
    
    if not review_api:
        return reviews
    
    enriched_reviews = []
    
    for review in reviews:
        enriched_review = review.copy()
        product_no = review.get('product_no')
        
        if product_no:
            # 캐시 확인
            if product_no not in product_cache:
                try:
                    product_info = review_api.get_product_info(product_no)
                    product_cache[product_no] = product_info.get('product_name', f'상품{product_no}')
                except Exception as e:
                    print(f"상품 {product_no} 정보 조회 실패: {e}")
                    product_cache[product_no] = f'상품{product_no}'
            
            enriched_review['product_name'] = product_cache[product_no]
        else:
            enriched_review['product_name'] = '알 수 없음'
        
        enriched_reviews.append(enriched_review)
    
    return enriched_reviews

def init_cafe24_client():
    """카페24 API 클라이언트 초기화 (OAuth 클라이언트 사용)"""
    global review_api
    
    # OAuth 클라이언트가 있고 토큰이 있는 경우 Review API 초기화
    if oauth_client:
        try:
            token_status = oauth_client.get_token_status()
            
            if token_status['has_token']:
                # Review API 클라이언트 초기화 (자동 갱신 기능 포함)
                review_api = Cafe24ReviewAPI(oauth_client)
                
                print(f"✅ 카페24 Review API 클라이언트 초기화 완료")
                print(f"   - Mall ID: {oauth_client.mall_id}")
                print(f"   - 토큰 상태: {token_status['message']}")
                
                # API 연결 테스트
                try:
                    boards = review_api.get_review_boards()
                    if boards:
                        print(f"📝 카페24 API 연결 테스트 성공! 리뷰 게시판 {len(boards)}개 발견")
                    else:
                        print("📝 카페24 API 연결은 성공했지만 리뷰 게시판을 찾을 수 없습니다.")
                except Exception as test_error:
                    print(f"⚠️ 카페24 API 연결 테스트 실패: {test_error}")
                    if "401" in str(test_error):
                        print("   토큰이 만료되었을 수 있습니다. 다음 요청 시 자동으로 갱신됩니다.")
                
            else:
                print(f"❌ 유효한 토큰이 없습니다: {token_status['message']}")
                print("   OAuth 인증을 통해 토큰을 발급받아주세요.")
                
        except Exception as e:
            print(f"❌ Review API 클라이언트 초기화 실패: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"❌ OAuth 클라이언트가 초기화되지 않았습니다.")
        print("   환경변수를 확인하고 OAuth 클라이언트를 먼저 초기화해주세요.")

# 모니터링 관련 전역 변수
monitoring_active = False
monitoring_thread = None
known_reviews = set()  # 이미 확인한 리뷰들 저장 (API용)
pending_notifications = []  # 대기 중인 알림들
DATA_FILE = 'known_reviews.json'

# 카페24 API 리뷰 캐시 시스템
REVIEW_CACHE_FILE = 'review_cache.json'
cached_reviews = []  # 최신 리뷰 10개 캐시

def load_model():
    global sentiment_analyzer
    try:
        # joblib로 저장된 scikit-learn 파이프라인 모델 로드
        import joblib
        model_path = 'lightweight_sentiment_model.pkl'
        print(f"경량 감정 분석 모델 로드 시작: {model_path}")
        
        sentiment_analyzer = joblib.load(model_path)
        print(f"경량 감정 분석 모델 로드 완료: {model_path}")
        print(f"모델 타입: {type(sentiment_analyzer)}")
        
    except Exception as e:
        print(f"❌ 경량 모델 로드 실패: {e}")
        sentiment_analyzer = None

def load_known_reviews():
    """저장된 기존 리뷰 목록 로드"""
    global known_reviews
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                known_reviews = set(data.get('reviews', []))
                print(f"기존 리뷰 {len(known_reviews)}개 로드 완료")
        else:
            known_reviews = set()
            print("새로운 모니터링 시작")
    except Exception as e:
        print(f"기존 리뷰 로드 오류: {e}")
        known_reviews = set()

def save_known_reviews():
    """현재 리뷰 목록 저장 (API용)"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'reviews': list(known_reviews),
                'last_updated': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"리뷰 저장 오류: {e}")

def load_review_cache():
    """저장된 리뷰 캐시 로드"""
    global cached_reviews
    try:
        if os.path.exists(REVIEW_CACHE_FILE):
            with open(REVIEW_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cached_reviews = data.get('reviews', [])
                print(f"리뷰 캐시 {len(cached_reviews)}개 로드 완료")
        else:
            cached_reviews = []
            print("새로운 리뷰 캐시 시작")
    except Exception as e:
        print(f"리뷰 캐시 로드 오류: {e}")
        cached_reviews = []

def save_review_cache():
    """현재 리뷰 캐시 저장"""
    try:
        with open(REVIEW_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'reviews': cached_reviews,
                'last_updated': datetime.now().isoformat(),
                'count': len(cached_reviews)
            }, f, ensure_ascii=False, indent=2)
        print(f"리뷰 캐시 {len(cached_reviews)}개 저장 완료")
    except Exception as e:
        print(f"리뷰 캐시 저장 오류: {e}")

def initialize_review_cache():
    """리뷰 캐시 초기화 - 최신 리뷰 10개로 캐시 설정"""
    global cached_reviews
    
    if not review_api:
        print("❌ Review API가 초기화되지 않았습니다.")
        return False
    
    try:
        print("🔄 리뷰 캐시 초기화 중...")
        latest_reviews = review_api.get_latest_reviews(limit=10)
        
        if latest_reviews:
            cached_reviews = latest_reviews
            save_review_cache()
            print(f"✅ 리뷰 캐시 초기화 완료: {len(cached_reviews)}개")
            return True
        else:
            print("⚠️ 초기화할 리뷰가 없습니다.")
            return False
    except Exception as e:
        print(f"❌ 리뷰 캐시 초기화 실패: {e}")
        return False

def find_new_reviews():
    """현재 최신 리뷰와 캐시 비교해서 신규 리뷰 찾기"""
    global cached_reviews
    
    if not review_api:
        return []
    
    try:
        # 현재 최신 리뷰 10개 조회
        current_reviews = review_api.get_latest_reviews(limit=10)
        if not current_reviews:
            return []
        
        # 캐시된 리뷰의 article_no들 추출
        cached_article_nos = {str(review.get('article_no', '')) for review in cached_reviews}
        
        # 신규 리뷰 찾기 (article_no 기준)
        new_reviews = []
        for review in current_reviews:
            article_no = str(review.get('article_no', ''))
            if article_no and article_no not in cached_article_nos:
                new_reviews.append(review)
        
        if new_reviews:
            print(f"🆕 신규 리뷰 {len(new_reviews)}개 발견!")
            
            # 캐시 업데이트: 신규 리뷰 추가하고 최신 10개만 유지
            all_reviews = new_reviews + cached_reviews
            cached_reviews = all_reviews[:10]  # 최신 10개만 유지
            save_review_cache()
            
        return new_reviews
        
    except Exception as e:
        print(f"신규 리뷰 찾기 오류: {e}")
        return []

def analyze_review(review_text):
    """단일 리뷰 감정 분석"""
    try:
        if sentiment_analyzer is None:
            load_model()
            
        if sentiment_analyzer is None:
            return {'is_negative': False, 'confidence': 0, 'error': '모델 로드 실패'}
        
        # scikit-learn 파이프라인 모델 사용
        try:
            # TfidfVectorizer + LogisticRegression 파이프라인인 경우
            if hasattr(sentiment_analyzer, 'predict_proba') and hasattr(sentiment_analyzer, 'predict'):
                
                # 예측 수행
                prediction = sentiment_analyzer.predict([review_text])
                prediction_proba = sentiment_analyzer.predict_proba([review_text])
                
                predicted_class = prediction[0]
                probabilities = prediction_proba[0]
                
                # 클래스 라벨 확인 (모델 학습 시 사용된 라벨)
                classes = sentiment_analyzer.classes_ if hasattr(sentiment_analyzer, 'classes_') else ['negative', 'positive']
                
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
                
            elif hasattr(sentiment_analyzer, 'predict'):
                # predict만 있는 경우
                prediction = sentiment_analyzer.predict([review_text])
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

def send_notification(new_reviews, negative_reviews):
    """신규 리뷰 알림 (콘솔 출력 + 브라우저 알림 준비)"""
    global pending_notifications
    
    print("\n" + "="*50)
    print("🚨 신규 리뷰 감지!")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"신규 리뷰: {len(new_reviews)}개")
    print(f"부정 리뷰: {len(negative_reviews)}개")
    print("="*50)
    
    # NotificationManager를 사용한 알림 추가
    notification_manager.add_review_notification(new_reviews, negative_reviews)
    
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
        pending_notifications.append({
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


# 기존 모니터링 루프는 제거하고 웹훅 기반으로만 동작

# ===== 카페24 OAuth 관련 엔드포인트 =====

@app.route('/auth/setup', methods=['GET', 'POST'])
def setup_auth():
    """카페24 API 설정"""
    if request.method == 'GET':
        # 현재 설정 상태 반환 (디버그 정보 포함)
        return jsonify({
            'configured': bool(settings.cafe24_client_id and settings.cafe24_client_secret),
            'mall_id': settings.cafe24_id,
            'redirect_uri': settings.cafe24_redirect_uri,
            'debug': {
                'has_client_id': bool(settings.cafe24_client_id),
                'has_client_secret': bool(settings.cafe24_client_secret),
                'client_id_preview': settings.cafe24_client_id[:10] + '...' if settings.cafe24_client_id else None,
                'oauth_client_initialized': bool(oauth_client)
            }
        })
    
    if request.method == 'POST':
        try:
            # settings는 이미 환경변수에서 로드됨
            if not settings.cafe24_client_id or not settings.cafe24_client_secret:
                return jsonify({'error': '환경변수에 CAFE24_CLIENT_ID와 CAFE24_CLIENT_SECRET을 설정해주세요.'}), 400
            
            # OAuth 클라이언트 초기화
            init_oauth_client()
            
            return jsonify({
                'message': '카페24 API 설정이 완료되었습니다.',
                'configured': True
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/auth/start')
def start_auth():
    """카페24 OAuth 인증 시작"""
    try:
        print(f"🚀 OAuth 인증 시작 요청")
        
        # OAuth 클라이언트 lazy 초기화
        client = get_or_create_oauth_client()
        if not client:
            return jsonify({'error': 'OAuth 클라이언트가 초기화되지 않았습니다.'}), 400
        
        # OAuth 인증 URL 생성
        auth_url, state = client.get_authorization_url(
            scope="mall.read_product,mall.read_category,mall.read_store,mall.read_community"
        )
        
        # 세션에 state 저장 (보안을 위해)
        session['oauth_state'] = state
        
        print(f"✅ 인증 URL 생성 완료:")
        print(f"   - URL: {auth_url}")
        print(f"   - State: {state}")
        
        return jsonify({
            'auth_url': auth_url,
            'state': state,
            'message': '브라우저에서 인증 URL을 열어 인증을 진행해주세요.',
            'open_window': True  # 프론트엔드에서 새 창으로 열도록 지시
        })
        
    except Exception as e:
        print(f"❌ OAuth 인증 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/process_callback', methods=['POST'])
def process_callback():
    """외부에서 전달받은 OAuth 콜백 처리"""
    try:
        data = request.json
        code = data.get('code')
        state = data.get('state')
        
        if not code:
            return jsonify({'error': '인증 코드가 없습니다.'}), 400
        
        if not oauth_client:
            return jsonify({'error': 'OAuth 클라이언트가 초기화되지 않았습니다.'}), 400
        
        # 액세스 토큰 발급
        token_data = oauth_client.get_access_token(code)
        
        # Review API 클라이언트 초기화
        global review_api
        from api import Cafe24ReviewAPI
        review_api = Cafe24ReviewAPI(oauth_client)
        
        # 리뷰 캐시 초기화
        if not cached_reviews:
            initialize_review_cache()
        
        # 알림 추가
        notification_manager.add_system_notification(
            "카페24 OAuth 인증이 완료되었습니다.", "success"
        )
        
        return jsonify({
            'message': '카페24 OAuth 인증이 완료되었습니다.',
            'token_expires_at': token_data.get('expires_at'),
            'scopes': token_data.get('scopes', [])
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/callback')
def oauth_callback():
    """카페24 OAuth 콜백 처리"""
    try:
        print(f"🔄 OAuth 콜백 수신:")
        
        # URL에서 코드와 state 추출
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        print(f"   - Code: {code[:20]}..." if code else "   - Code: None")
        print(f"   - State: {state}")
        print(f"   - Error: {error}")
        print(f"   - 세션 State: {session.get('oauth_state')}")
        
        if error:
            print(f"❌ OAuth 인증 오류: {error}")
            error_descriptions = {
                'access_denied': '사용자가 권한을 거부했습니다.',
                'invalid_request': '잘못된 요청입니다.',
                'server_error': '카페24 서버 오류가 발생했습니다.'
            }
            error_msg = error_descriptions.get(error, f'인증 오류: {error}')
            
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>카페24 OAuth 인증 거부</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                    .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                    .detail {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                    .close-btn {{ background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
                </style>
            </head>
            <body>
                <div class="error">❌ 카페24 OAuth 인증 거부</div>
                <div class="message">OAuth 인증이 거부되었거나 오류가 발생했습니다.</div>
                <div class="detail">
                    <strong>오류 코드:</strong> {error}<br>
                    <strong>상세 내용:</strong> {error_msg}
                </div>
                <button class="close-btn" onclick="window.close()">창 닫기</button>
                <script>
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            return error_html
        
        if not code:
            print(f"❌ 인증 코드가 없습니다.")
            
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>카페24 OAuth 인증 실패</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                    .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                    .detail {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                    .close-btn {{ background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
                </style>
            </head>
            <body>
                <div class="error">❌ 카페24 OAuth 인증 실패</div>
                <div class="message">OAuth 인증 과정에서 문제가 발생했습니다.</div>
                <div class="detail">
                    <strong>오류 내용:</strong><br>
                    인증 코드가 전달되지 않았습니다. 다시 시도해주세요.
                </div>
                <button class="close-btn" onclick="window.close()">창 닫기</button>
                <script>
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            return error_html
        
        # state 검증
        if state != session.get('oauth_state'):
            print(f"❌ State 불일치: 받은={state}, 저장된={session.get('oauth_state')}")
            
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>카페24 OAuth 보안 오류</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                    .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                    .detail {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                    .close-btn {{ background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
                    .security {{ color: #721c24; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="error">❌ 카페24 OAuth 보안 오류</div>
                <div class="message">보안 검증에 실패했습니다.</div>
                <div class="detail">
                    <div class="security">⚠️ CSRF 공격 의심</div><br>
                    <strong>오류 내용:</strong><br>
                    인증 상태가 유효하지 않습니다. 세션이 변조되었거나 CSRF 공격일 가능성이 있습니다.<br><br>
                    <strong>받은 State:</strong> {state}<br>
                    <strong>예상 State:</strong> {session.get('oauth_state')}
                </div>
                <button class="close-btn" onclick="window.close()">창 닫기</button>
                <script>
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            return error_html
        
        # OAuth 클라이언트 lazy 초기화 
        client = get_or_create_oauth_client()
        if not client:
            print(f"❌ OAuth 클라이언트가 없습니다.")
            
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>카페24 OAuth 설정 오류</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                    .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                    .detail {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                    .close-btn {{ background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
                    .config {{ color: #856404; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="error">❌ 카페24 OAuth 설정 오류</div>
                <div class="message">OAuth 클라이언트 초기화에 실패했습니다.</div>
                <div class="detail">
                    <div class="config">🔧 설정 확인 필요</div><br>
                    <strong>오류 내용:</strong><br>
                    OAuth 클라이언트가 초기화되지 않았습니다.<br><br>
                    <strong>확인 사항:</strong><br>
                    • .env 파일의 CAFE24_CLIENT_ID 설정<br>
                    • .env 파일의 CAFE24_CLIENT_SECRET 설정<br>
                    • .env 파일의 CAFE24_REDIRECT_URI 설정<br>
                    • 서버 재시작 필요 여부
                </div>
                <button class="close-btn" onclick="window.close()">창 닫기</button>
                <script>
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            return error_html
        
        print(f"🔐 액세스 토큰 발급 중...")
        
        # 액세스 토큰 발급
        try:
            token_data = client.get_access_token(code)
            if not token_data or not token_data.get('access_token'):
                raise Exception("토큰 발급 실패: 토큰 데이터가 없습니다.")
            print(f"✅ 토큰 발급 완료: {token_data}")
            
        except Exception as token_error:
            print(f"❌ 토큰 발급 실패: {token_error}")
            
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>카페24 토큰 발급 오류</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                    .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                    .detail {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                    .close-btn {{ background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
                    .token {{ color: #721c24; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="error">❌ 카페24 토큰 발급 오류</div>
                <div class="message">액세스 토큰 발급에 실패했습니다.</div>
                <div class="detail">
                    <div class="token">🔑 토큰 발급 실패</div><br>
                    <strong>오류 내용:</strong><br>
                    {str(token_error)}<br><br>
                    <strong>가능한 원인:</strong><br>
                    • 만료된 인증 코드<br>
                    • 잘못된 카페24 API 설정<br>
                    • 네트워크 연결 문제<br>
                    • 카페24 서버 오류<br><br>
                    <strong>해결 방법:</strong><br>
                    다시 인증을 시도해주세요.
                </div>
                <button class="close-btn" onclick="window.close()">창 닫기</button>
                <script>
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            return error_html
        
        # Review API 클라이언트 초기화
        global review_api
        review_api = Cafe24ReviewAPI(client)
        print(f"📝 Review API 클라이언트 초기화 완료")
        
        # 세션 정리
        session.pop('oauth_state', None)
        
        # 알림 추가
        notification_manager.add_system_notification(
            "카페24 OAuth 인증이 완료되었습니다.", "success"
        )
        
        print(f"🎉 OAuth 인증 성공!")
        
        # 성공 페이지 반환
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>카페24 OAuth 인증 완료</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .success {{ color: #28a745; font-size: 24px; margin-bottom: 20px; }}
                .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                .detail {{ background: #d4edda; padding: 15px; border-radius: 5px; margin: 20px; }}
                .close-btn {{ background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="success">✅ 카페24 OAuth 인증 완료!</div>
            <div class="message">API 접근 권한이 성공적으로 설정되었습니다.</div>
            <div class="detail">
                <strong>권한 범위:</strong> {', '.join(token_data.get('scopes', []))}<br>
                <strong>토큰 만료:</strong> {token_data.get('expires_at', 'Unknown')}
            </div>
            <button class="close-btn" onclick="window.close()">창 닫기</button>
            <script>
                setTimeout(() => {{
                    window.close();
                }}, 3000);
            </script>
        </body>
        </html>
        """
        return success_html
        
    except Exception as e:
        print(f"❌ OAuth 콜백 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        
        # 예외 발생 시 에러 페이지
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>카페24 OAuth 오류</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                .detail {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                .close-btn {{ background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="error">❌ 카페24 OAuth 처리 중 오류 발생</div>
            <div class="message">시스템 오류가 발생했습니다.</div>
            <div class="detail">
                <strong>오류 내용:</strong><br>
                {str(e)}
            </div>
            <button class="close-btn" onclick="window.close()">창 닫기</button>
            <script>
                setTimeout(() => {{
                    window.close();
                }}, 10000);
            </script>
        </body>
        </html>
        """
        return error_html

# 카카오톡 알림 관련 엔드포인트
@app.route('/auth/kakao/start')
def start_kakao_auth():
    """카카오톡 인증 시작"""
    try:
        auth_url = notification_manager.get_kakao_auth_url()
        if not auth_url:
            return jsonify({'error': '카카오 API 키가 설정되지 않았습니다.'}), 400
            
        return jsonify({
            'auth_url': auth_url,
            'message': '카카오톡 인증을 위해 브라우저에서 URL을 열어주세요.'
        })
        
    except Exception as e:
        print(f"❌ 카카오톡 인증 시작 실패: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/auth/kakao/callback')
def kakao_callback():
    """카카오톡 OAuth 콜백 처리"""
    try:
        code = request.args.get('code')
        error = request.args.get('error')
        
        if error:
            print(f"❌ 카카오톡 인증 오류: {error}")
            return jsonify({'error': f'카카오톡 인증 오류: {error}'}), 400
            
        if not code:
            return jsonify({'error': '인증 코드가 없습니다.'}), 400
            
        # 액세스 토큰 발급
        access_token = notification_manager.get_kakao_access_token(code)
        
        if access_token:
            # 토큰 정보 확인 (디버깅용)
            has_refresh = hasattr(notification_manager, 'kakao_refresh_token') and notification_manager.kakao_refresh_token
            
            # 테스트 메시지 전송
            test_message = "🎉 카카오톡 알림 설정이 완료되었습니다!\n부정 리뷰 발견 시 이곳으로 알림이 전송됩니다."
            notification_manager.send_kakao_message(test_message)
            
            # 팝업 창 자동 닫기를 위한 HTML 응답 (토큰 정보 포함)
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>카카오톡 인증 완료</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .success {{ color: #28a745; font-size: 24px; margin-bottom: 20px; }}
                    .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                    .debug {{ background: #f8f9fa; padding: 15px; margin: 20px; border-radius: 5px; font-size: 14px; text-align: left; }}
                </style>
            </head>
            <body>
                <div class="success">✅ 카카오톡 인증 완료!</div>
                <div class="message">카카오톡으로 테스트 메시지가 전송되었습니다.<br>이 창은 자동으로 닫힙니다.</div>
                <div class="debug">
                    <strong>토큰 정보:</strong><br>
                    액세스 토큰: {access_token[:10]}...<br>
                    리프레시 토큰: {'있음' if has_refresh else '없음'}<br>
                    저장 상태: 메모리에 저장됨
                </div>
                <script>
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            return html_response
        else:
            # 토큰 발급 실패 시 에러 페이지
            error_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>카카오톡 인증 실패</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .error { color: #dc3545; font-size: 24px; margin-bottom: 20px; }
                    .message { color: #666; font-size: 16px; margin-bottom: 30px; }
                    .retry-btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
                </style>
            </head>
            <body>
                <div class="error">❌ 카카오톡 인증 실패</div>
                <div class="message">액세스 토큰 발급에 실패했습니다.<br>잠시 후 다시 시도해주세요.</div>
                <button class="retry-btn" onclick="window.close()">창 닫기</button>
            </body>
            </html>
            """
            return error_html
            
    except Exception as e:
        print(f"❌ 카카오톡 콜백 처리 실패: {e}")
        
        # 예외 발생 시 에러 페이지
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>카카오톡 인증 오류</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                .message {{ color: #666; font-size: 16px; margin-bottom: 20px; }}
                .detail {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px; text-align: left; }}
                .retry-btn {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="error">❌ 카카오톡 인증 중 오류 발생</div>
            <div class="message">시스템 오류가 발생했습니다.</div>
            <div class="detail">
                <strong>오류 내용:</strong><br>
                {str(e)}
            </div>
            <button class="retry-btn" onclick="window.close()">창 닫기</button>
            <script>
                setTimeout(() => {{
                    window.close();
                }}, 10000);
            </script>
        </body>
        </html>
        """
        return error_html

@app.route('/auth/kakao/status')
def kakao_auth_status():
    """카카오톡 인증 상태 확인"""
    try:
        # 카카오 API 키가 설정되어 있고 액세스 토큰이 있으면 인증 완료
        api_key_configured = bool(notification_manager.kakao_api_key)
        access_token_available = notification_manager.kakao_access_token is not None
        
        authenticated = api_key_configured and access_token_available
        
        print(f"🔍 카카오톡 상태 확인:")
        print(f"   API 키: {'설정됨' if api_key_configured else '미설정'} ({notification_manager.kakao_api_key[:10] if notification_manager.kakao_api_key else 'None'}...)")
        print(f"   액세스 토큰: {'있음' if access_token_available else '없음'}")
        print(f"   인증 상태: {'완료' if authenticated else '미완료'}")
        
        return jsonify({
            'authenticated': authenticated,
            'api_key_configured': api_key_configured,
            'access_token_available': access_token_available,
            'message': '카카오톡 인증 완료' if authenticated else '카카오톡 인증 필요'
        })
        
    except Exception as e:
        print(f"❌ 카카오톡 인증 상태 확인 실패: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/test/kakao-notification', methods=['POST'])
def test_kakao_notification():
    """카카오톡 알림 테스트"""
    try:
        data = request.json or {}
        message = data.get('message', '카카오톡 알림 테스트 메시지입니다! 🎉')
        
        print(f"🔍 카카오톡 테스트 메시지 전송 시도: {message[:50]}...")
        print(f"🔍 액세스 토큰 상태: {'있음' if notification_manager.kakao_access_token else '없음'}")
        print(f"🔍 API 키 상태: {'있음' if notification_manager.kakao_api_key else '없음'}")
        
        # 액세스 토큰이 없으면 구체적인 오류 메시지 반환
        if not notification_manager.kakao_access_token:
            print("❌ 카카오톡 액세스 토큰이 없습니다.")
            return jsonify({'error': '카카오톡 인증이 필요합니다. 먼저 카카오톡 연동을 완료해주세요.'}), 400
        
        success = notification_manager.send_kakao_message(message)
        
        if success:
            print("✅ 카카오톡 테스트 메시지 전송 성공")
            return jsonify({
                'message': '카카오톡 테스트 메시지가 전송되었습니다.',
                'success': True
            })
        else:
            print("❌ 카카오톡 메시지 전송 실패 - send_kakao_message returned False")
            return jsonify({'error': '카카오톡 메시지 전송에 실패했습니다. 토큰이 만료되었거나 API 오류가 발생했습니다.'}), 400
            
    except Exception as e:
        print(f"❌ 카카오톡 테스트 메시지 전송 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'서버 오류: {str(e)}'}), 500

@app.route('/auth/status')
def auth_status():
    """인증 상태 확인"""
    try:
        if not oauth_client:
            return jsonify({
                'configured': False,
                'authenticated': False,
                'message': '카페24 API 설정이 필요합니다.'
            })
        
        token_status = oauth_client.get_token_status()
        
        return jsonify({
            'configured': True,
            'authenticated': token_status['has_token'],
            'token_valid': token_status['status'] == 'valid',
            'status': token_status['status'],
            'message': token_status['message'],
            'issued_at': token_status.get('issued_at'),
            'expires_at': token_status.get('expires_at'),
            'scopes': token_status.get('scopes', [])
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/manual_token', methods=['POST'])
def manual_token_setup():
    """수동으로 토큰 설정"""
    try:
        data = request.json
        access_token = data.get('access_token', '').strip()
        refresh_token = data.get('refresh_token', '').strip()
        expires_at = data.get('expires_at', '')
        scopes = data.get('scopes', [])
        
        if not access_token:
            return jsonify({'error': 'Access Token을 입력해주세요.'}), 400
        
        if not oauth_client:
            return jsonify({'error': '카페24 API 설정을 먼저 완료해주세요.'}), 400
        
        # 토큰 데이터 구성
        token_data = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at,
            'scopes': scopes,
            'expires_in_seconds': 7200,
            'issued_at': datetime.now().isoformat(),
            'client_id': oauth_client.client_id,
            'mall_id': oauth_client.mall_id,
            'user_id': 'manual_setup'
        }
        
        # 토큰 저장
        oauth_client.save_tokens(token_data)
        
        # Review API 클라이언트 초기화
        global review_api
        review_api = Cafe24ReviewAPI(oauth_client)
        
        # 알림 추가
        notification_manager.add_system_notification(
            "카페24 API 토큰이 수동으로 설정되었습니다.", "success"
        )
        
        return jsonify({
            'message': '토큰이 성공적으로 설정되었습니다.',
            'expires_at': expires_at,
            'scopes': scopes
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/revoke', methods=['POST'])
def revoke_token():
    """토큰 폐기"""
    try:
        if not oauth_client:
            return jsonify({'error': 'OAuth 클라이언트가 초기화되지 않았습니다.'}), 400
        
        result = oauth_client.revoke_token()
        
        if result:
            # Review API 클라이언트 제거
            global review_api
            review_api = None
            
            notification_manager.add_system_notification(
                "카페24 API 토큰이 폐기되었습니다.", "warning"
            )
            
            return jsonify({'message': '토큰이 성공적으로 폐기되었습니다.'})
        else:
            return jsonify({'error': '토큰 폐기에 실패했습니다.'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== 카페24 API 리뷰 관련 엔드포인트 =====

@app.route('/api/reviews/boards')
@full_auth_required
def get_review_boards():
    """리뷰 게시판 목록 조회"""
    try:
        boards = review_api.get_review_boards()
        
        return jsonify({
            'boards': boards,
            'count': len(boards)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/latest')
@full_auth_required
def get_latest_reviews():
    """최신 리뷰 조회"""
    try:
        days = request.args.get('days', 7, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        reviews = review_api.get_latest_reviews(days=days, limit=limit)
        
        # 감정 분석 수행
        if reviews:
            analyzed_reviews = analyze_reviews_batch(reviews)
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews)
            statistics = get_review_statistics(enriched_reviews)
            negative_reviews = get_negative_reviews(enriched_reviews)
            
            return jsonify({
                'reviews': enriched_reviews,
                'statistics': statistics,
                'negative_reviews': negative_reviews[:10],  # 상위 10개
                'count': len(enriched_reviews)
            })
        else:
            return jsonify({
                'reviews': [],
                'statistics': get_review_statistics([]),
                'negative_reviews': [],
                'count': 0
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/product/<int:product_no>')
@full_auth_required
def get_product_reviews(product_no):
    """특정 상품의 리뷰 조회"""
    try:
        limit = request.args.get('limit', 100, type=int)
        
        reviews = review_api.get_product_reviews(product_no=product_no, limit=limit)
        
        if reviews:
            analyzed_reviews = analyze_reviews_batch(reviews)
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews)
            statistics = get_review_statistics(enriched_reviews)
            negative_reviews = get_negative_reviews(enriched_reviews)
            
            return jsonify({
                'product_no': product_no,
                'reviews': enriched_reviews,
                'statistics': statistics,
                'negative_reviews': negative_reviews,
                'count': len(enriched_reviews)
            })
        else:
            return jsonify({
                'product_no': product_no,
                'reviews': [],
                'statistics': get_review_statistics([]),
                'negative_reviews': [],
                'count': 0,
                'message': '해당 상품의 리뷰를 찾을 수 없습니다.'
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/search')
@full_auth_required
def search_reviews():
    """리뷰 검색"""
    try:
        keyword = request.args.get('keyword', '').strip()
        limit = request.args.get('limit', 50, type=int)
        
        if not keyword:
            return jsonify({'error': '검색 키워드를 입력해주세요.'}), 400
        
        reviews = review_api.search_reviews(keyword=keyword, limit=limit)
        
        if reviews:
            analyzed_reviews = analyze_reviews_batch(reviews)
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews)
            statistics = get_review_statistics(enriched_reviews)
            negative_reviews = get_negative_reviews(enriched_reviews)
            
            return jsonify({
                'keyword': keyword,
                'reviews': enriched_reviews,
                'statistics': statistics,
                'negative_reviews': negative_reviews,
                'count': len(enriched_reviews)
            })
        else:
            return jsonify({
                'keyword': keyword,
                'reviews': [],
                'statistics': get_review_statistics([]),
                'negative_reviews': [],
                'count': 0,
                'message': f"'{keyword}'에 대한 리뷰를 찾을 수 없습니다."
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products')
@full_auth_required
def get_products():
    """상품 목록 조회"""
    try:
        limit = request.args.get('limit', 100, type=int)
        
        products = review_api.get_products(limit=limit)
        
        return jsonify({
            'products': products,
            'count': len(products)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== 로그인 엔드포인트 =====

@app.route('/login', methods=['POST'])
def login():
    """로그인 처리"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'error': '아이디와 패스워드를 입력해주세요.'}), 400
        
        if verify_credentials(username, password):
            # 사용자 정보 세션에 저장
            session['user'] = {
                'id': 'admin',
                'username': username,
                'name': 'Cilantro',
                'picture': None
            }
            
            # 알림 추가
            notification_manager.add_system_notification(
                f"{username} 관리자가 로그인했습니다.", "success"
            )
            
            return jsonify({
                'message': '로그인 성공',
                'user': session['user']
            })
        else:
            return jsonify({'error': '아이디 또는 패스워드가 올바르지 않습니다.'}), 401
        
    except Exception as e:
        return jsonify({'error': f'로그인 실패: {str(e)}'}), 500

@app.route('/logout', methods=['POST'])
def logout():
    """로그아웃"""
    try:
        user_name = session.get('user', {}).get('username', '사용자')
        session.pop('user', None)
        
        # 알림 추가
        notification_manager.add_system_notification(
            f"{user_name}님이 로그아웃했습니다.", "info"
        )
        
        return jsonify({'message': '로그아웃되었습니다.'})
        
    except Exception as e:
        return jsonify({'error': f'로그아웃 실패: {str(e)}'}), 500

@app.route('/user/status')
def user_auth_status():
    """사용자 인증 상태 확인"""
    try:
        if 'user' in session:
            return jsonify({
                'authenticated': True,
                'user': session['user']
            })
        else:
            return jsonify({
                'authenticated': False,
                'user': None
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== 채널톡 웹훅 엔드포인트 =====

@app.route('/webhook/channel-talk', methods=['POST'])
@app.route('/webhook/channel-tal', methods=['POST'])
def cafe24_webhook():
    """카페24 웹훅 수신"""
    try:
        # 웹훅 활성화 여부 확인
        if not WEBHOOK_ENABLED:
            return jsonify({'error': '웹훅이 비활성화되었습니다.'}), 403
        
        # 카페24 웹훅인지 확인 (헤더 또는 요청 내용으로 구분)
        user_agent = request.headers.get('User-Agent', '')
        
        # 카페24 웹훅은 이벤트 키 검증 대신 verification code 사용
        # 일단 모든 요청을 허용 (나중에 verification 추가 가능)
        print(f"카페24 웹훅 수신 - User-Agent: {user_agent}")
        print(f"요청 헤더들: {dict(request.headers)}")
        
        # 웹훅 데이터 파싱
        webhook_data = request.json
        
        if not webhook_data:
            return jsonify({'error': '웹훅 데이터가 없습니다.'}), 400
        
        print(f"카페24 웹훅 수신: {webhook_data}")
        
        # 카페24 웹훅 처리 (게시판 글 등록)
        success = process_cafe24_webhook(webhook_data)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': '웹훅 처리 완료',
                'processed_at': datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                'status': 'ignored',
                'message': '처리 대상이 아닌 이벤트'
            }), 200
        
    except Exception as e:
        print(f"채널톡 웹훅 처리 중 오류: {e}")
        return jsonify({'error': '웹훅 처리 중 오류가 발생했습니다.'}), 500

@app.route('/webhook/test', methods=['POST'])
@login_required
def test_webhook():
    """웹훅 테스트용 엔드포인트"""
    try:
        test_data = request.json or {}
        
        # 테스트 데이터 생성
        test_webhook_data = {
            'eventType': 'review.created',
            'data': {
                'content': test_data.get('content', '이 제품 정말 별로네요. 품질도 안좋고 배송도 늦어요.'),
                'author': {'name': test_data.get('author', 'Test User')},
                'rating': test_data.get('rating', 2),
                'product': {'name': 'Test Product'},
                'createdAt': datetime.now().isoformat()
            }
        }
        
        # 웹훅 처리 테스트
        success = process_channel_talk_webhook(test_webhook_data)
        
        return jsonify({
            'status': 'test_completed',
            'webhook_data': test_webhook_data,
            'processed': success,
            'message': '웹훅 테스트가 완료되었습니다.'
        })
        
    except Exception as e:
        return jsonify({'error': f'웹훅 테스트 오류: {str(e)}'}), 500

@app.route('/webhook/status')
@login_required
def webhook_status():
    """웹훅 상태 조회"""
    try:
        return jsonify({
            'enabled': WEBHOOK_ENABLED,
            'event_key_configured': bool(WEBHOOK_EVENT_KEY),
            'event_key_value': WEBHOOK_EVENT_KEY if WEBHOOK_EVENT_KEY else 'Not configured',
            'endpoint': url_for('channel_talk_webhook', _external=True),
            'test_endpoint': url_for('test_webhook', _external=True),
            'recent_notifications': notification_manager.get_recent_notifications(limit=5)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== 기존 엔드포인트들 =====

@app.route('/')
def index():
    return render_template('index.html')



@app.route('/webhook/init', methods=['POST'])
@login_required
def init_webhook_system():
    """웹훅 기반 시스템 초기화"""
    global monitoring_active
    
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        # 웹훅 시스템 활성화
        monitoring_active = True
        
        # 기존 리뷰 데이터 로드
        load_known_reviews()
        
        # 리뷰 캐시 초기화
        if not cached_reviews:
            print("리뷰 캐시 초기화 중...")
            initialize_review_cache()
        
        # 알림 추가
        notification_manager.add_monitoring_notification(
            'webhook_ready', 
            "웹훅 기반 리뷰 모니터링 시스템이 준비되었습니다",
            {'type': 'webhook_system', 'cached_reviews': len(cached_reviews)}
        )
        
        return jsonify({
            'message': '웹훅 기반 리뷰 모니터링 시스템이 준비되었습니다.',
            'type': 'webhook',
            'cached_reviews': len(cached_reviews),
            'webhook_enabled': True
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """모니터링 정지"""
    global monitoring_active, monitoring_thread
    
    try:
        if not monitoring_active:
            return jsonify({'error': '모니터링이 실행 중이지 않습니다.'}), 400
        
        monitoring_active = False
        
        # 알림 추가
        notification_manager.add_monitoring_notification(
            'stopped', 
            "리뷰 모니터링이 정지되었습니다."
        )
        
        return jsonify({
            'message': '모니터링이 정지되었습니다.'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/monitoring_status')
def monitoring_status():
    """모니터링 상태 확인"""
    return jsonify({
        'active': monitoring_active,
        'type': 'webhook_based',
        'known_reviews_count': len(known_reviews),
        'cached_reviews_count': len(cached_reviews),
        'webhook_enabled': WEBHOOK_ENABLED,
        'webhook_event_key_configured': bool(settings.WEBHOOK_EVENT_KEY)
    })

@app.route('/get_notifications')
def get_notifications():
    """대기 중인 알림 가져가기"""
    try:
        # NotificationManager에서 알림 가져오기
        notifications = notification_manager.get_pending_notifications(mark_as_read=True)
        
        # 기존 pending_notifications도 포함 (하위 호환성)
        global pending_notifications
        if pending_notifications:
            notifications.extend(pending_notifications)
            pending_notifications.clear()
        
        return jsonify({
            'notifications': notifications,
            'count': len(notifications)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/notifications/recent')
def get_recent_notifications():
    """최근 알림 기록 조회"""
    try:
        limit = request.args.get('limit', 10, type=int)
        recent = notification_manager.get_recent_notifications(limit=limit)
        
        return jsonify({
            'notifications': recent,
            'count': len(recent)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/notifications/statistics')
def get_notification_statistics():
    """알림 통계 정보"""
    try:
        statistics = notification_manager.get_statistics()
        return jsonify(statistics)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/config', methods=['GET'])
def get_config():
    """현재 설정 조회"""
    try:
        return jsonify({
            'cafe24': {
                'client_id': settings.cafe24_client_id,
                'mall_id': settings.cafe24_id,
                'redirect_uri': settings.cafe24_redirect_uri,
                'configured': bool(settings.cafe24_client_id and settings.cafe24_client_secret)
            },
            'monitoring': {
                'check_interval': settings.check_interval,
                'max_reviews_per_check': settings.max_reviews_per_check,
                'notification_enabled': settings.notification_enabled
            },
            'app': {
                'debug': settings.debug,
                'port': settings.port,
                'host': settings.host
            },
            'webhook': {
                'enabled': WEBHOOK_ENABLED,
                'event_key_configured': bool(settings.WEBHOOK_EVENT_KEY)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("서버 시작 중...")
    
    # 메모리 절약을 위해 모델을 즉시 로드하지 않음 (lazy loading)
    print("감정 분석 모델은 첫 번째 요청 시 로드됩니다.")
    
    # 설정 상태 출력 및 검증
    print("=== 설정 상태 ===")
    
    # 필수 설정 검증
    required_settings = []
    
    if not settings.cafe24_client_id:
        required_settings.append("CAFE24_CLIENT_ID")
    if not settings.cafe24_client_secret:
        required_settings.append("CAFE24_CLIENT_SECRET")  
    if not settings.cafe24_id:
        required_settings.append("CAFE24_ID")
    if not settings.cafe24_password:
        required_settings.append("CAFE24_PASSWORD")
    if not settings.cafe24_redirect_uri:
        required_settings.append("CAFE24_REDIRECT_URI")
    if not settings.WEBHOOK_EVENT_KEY:
        required_settings.append("WEBHOOK_EVENT_KEY")
    if not settings.SERVICE_KEY:
        required_settings.append("SERVICE_KEY")
        
    if required_settings:
        print("❌ 필수 환경변수가 설정되지 않았습니다:")
        for setting in required_settings:
            print(f"   - {setting}")
        print("\n환경변수를 설정한 후 서버를 재시작해주세요.")
        print("예: export CAFE24_CLIENT_ID=your_client_id")
    else:
        print("✅ 모든 필수 환경변수가 설정되었습니다.")
    
    print(f"카페24 Mall ID (cafe24_id): {settings.cafe24_id}")
    print(f"카페24 Client ID: {settings.cafe24_client_id}")
    print(f"카페24 Redirect URI: {settings.cafe24_redirect_uri}")
    print(f"웹훅 이벤트 키: {'설정됨' if settings.WEBHOOK_EVENT_KEY else '미설정'}")
    print(f"서비스 키: {'설정됨' if settings.SERVICE_KEY else '미설정'}")
    
    
    # 카페24 OAuth 클라이언트 초기화
    init_oauth_client()
    
    # 카페24 Review API 클라이언트 초기화
    init_cafe24_client()
    
    # 리뷰 캐시 시스템 초기화
    print("=== 리뷰 캐시 시스템 초기화 ===")
    load_review_cache()
    
    # Review API가 있으면 캐시 초기화 또는 업데이트
    if review_api:
        if not cached_reviews:
            print("캐시가 비어있어서 초기화를 시도합니다...")
            initialize_review_cache()
        else:
            print(f"기존 캐시 {len(cached_reviews)}개를 사용합니다.")
    print()
    
    
    # 프로덕션에서는 Gunicorn이 앱을 실행하므로 app.run() 제거
    # 개발환경에서만 직접 실행
    if settings.debug and __name__ == '__main__':
        port = int(os.environ.get('PORT', settings.port))
        app.run(
            debug=True, 
            port=port,
            host=settings.host
        )