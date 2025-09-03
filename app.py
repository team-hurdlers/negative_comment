from flask import Flask, request, jsonify, render_template, redirect, session, url_for
from flask_cors import CORS
from transformers import pipeline
from crawler import ShoppingMallCrawler
from auth import Cafe24OAuth
from api import Cafe24ReviewAPI, ReviewAnalyzer
from utils import ConfigManager, NotificationManager
import warnings
import threading
import time
import json
import os
import requests
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from functools import wraps
try:
    from dotenv import load_dotenv
    load_dotenv()  # .env 파일 로드
except ImportError:
    pass

# Settings 클래스 import
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        # config.json 파일 로드
        self.config = self.load_config()
        
        # 환경변수에서 로드
        self.SERVICE_KEY = os.getenv("SERVICE_KEY")
        self.WEBHOOK_EVENT_KEY = os.getenv("WEBHOOK_EVENT_KEY")
        self.cafe24_password = os.getenv("CAFE24_PASSWORD")
        self.cafe24_access_token = os.getenv("CAFE24_ACCESS_TOKEN")
        self.cafe24_refresh_token = os.getenv("CAFE24_REFRESH_TOKEN")
        
        # config.json에서 cafe24 설정 로드
        cafe24_config = self.config.get('cafe24', {})
        self.cafe24_client_id = cafe24_config.get('client_id') or os.getenv("CAFE24_CLIENT_ID")
        self.cafe24_client_secret = cafe24_config.get('client_secret') or os.getenv("CAFE24_CLIENT_SECRET")
        self.cafe24_mall_id = cafe24_config.get('mall_id') or os.getenv("CAFE24_ID")
        self.redirect_uri = cafe24_config.get('redirect_uri', "https://cafe24-oauth-final.loca.lt/callback")
        
        # 하위 호환성을 위해 cafe24_id 유지
        self.cafe24_id = self.cafe24_mall_id
    
    def load_config(self):
        """config.json 파일 로드"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"config.json 로드 실패: {e}")
            return {}

settings = Settings()
warnings.filterwarnings('ignore')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# 설정 및 관리자 초기화
config = ConfigManager()
notification_manager = NotificationManager()

# 로그인 설정 (환경변수에서 로드)
ADMIN_USERNAME = settings.cafe24_id or 'cila01'
ADMIN_PASSWORD = settings.cafe24_password or 'cila01'

# 채널톡 웹훅 설정
WEBHOOK_EVENT_KEY = settings.WEBHOOK_EVENT_KEY
WEBHOOK_ENABLED = True

# OAuth 클라이언트 (나중에 설정에서 초기화)
oauth_client = None
review_api = None
analyzer = ReviewAnalyzer()

sentiment_analyzer = None
crawler = ShoppingMallCrawler()

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

def verify_credentials(username, password):
    """사용자 인증 확인"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

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
            analyzed_reviews = analyzer.analyze_reviews_batch(new_reviews)
            negative_reviews = [r for r in analyzed_reviews if r.get('is_negative', False)]
            
            if negative_reviews:
                print(f"🚨 신규 부정 리뷰 {len(negative_reviews)}개 발견!")
                
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

# OAuth 클라이언트 초기화 함수
class SimpleCafe24API:
    """간단한 카페24 API 클라이언트 (직접 토큰 사용)"""
    
    def __init__(self, mall_id, access_token, refresh_token=None):
        self.mall_id = mall_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.base_url = f"https://{mall_id}.cafe24api.com/api/v2"
        
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'X-Cafe24-Api-Version': '2022-03-01'
        }
    
    def get_products(self, limit=10):
        """상품 목록 조회"""
        try:
            url = f"{self.base_url}/admin/products"
            params = {'limit': limit}
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            print(f"상품 조회 오류: {e}")
            return None
    
    def get_reviews(self, limit=10):
        """리뷰 목록 조회"""
        try:
            url = f"{self.base_url}/admin/boards/review/articles"
            params = {'limit': limit}
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            print(f"리뷰 조회 오류: {e}")
            return None

def init_cafe24_client():
    """카페24 API 클라이언트 초기화 (직접 토큰 사용)"""
    global review_api
    
    if settings.cafe24_access_token and settings.cafe24_mall_id:
        try:
            review_api = SimpleCafe24API(
                mall_id=settings.cafe24_mall_id,
                access_token=settings.cafe24_access_token,
                refresh_token=settings.cafe24_refresh_token
            )
            
            print(f"✅ 카페24 API 클라이언트 초기화 완료")
            print(f"   - Mall ID: {settings.cafe24_mall_id}")
            print(f"   - Access Token: {settings.cafe24_access_token[:20]}...")
            
            # API 연결 테스트
            test_result = review_api.get_products(limit=1)
            if test_result:
                print("📝 카페24 API 연결 테스트 성공!")
            else:
                print("⚠️  카페24 API 연결 테스트 실패 - 토큰이 만료되었을 수 있습니다.")
                
        except Exception as e:
            print(f"❌  클라이언트 초기화 실패: {e}")
            import traceback
            traceback.print_exc()
    else:
        missing = []
        if not settings.cafe24_access_token:
            missing.append("CAFE24_ACCESS_TOKEN")
        if not settings.cafe24_mall_id:
            missing.append("CAFE24_MALL_ID")
        
        print(f"❌  설정이 완료되지 않았습니다. 누락: {', '.join(missing)}")
        print("   환경변수에 CAFE24_ACCESS_TOKEN과 CAFE24_MALL_ID를 설정해주세요.")

# 모니터링 관련 전역 변수
monitoring_active = False
monitoring_thread = None
monitored_url = None
known_reviews = set()  # 이미 확인한 리뷰들 저장 (URL 크롤링용)
pending_notifications = []  # 대기 중인 알림들
DATA_FILE = 'known_reviews.json'

# 카페24 API 리뷰 캐시 시스템
REVIEW_CACHE_FILE = 'review_cache.json'
cached_reviews = []  # 최신 리뷰 10개 캐시

def load_model():
    global sentiment_analyzer
    try:
        # 한국어 감정 분석에 특화된 모델 사용
        sentiment_analyzer = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            device=-1
        )
        print("다국어 감정 분석 모델 로드 완료")
    except Exception as e:
        print(f"다국어 모델 로드 실패, 기본 모델 시도: {e}")
        try:
            # 백업으로 기본 모델 사용
            sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                device=-1
            )
            print("영어 감정 분석 모델 로드 완료")
        except Exception as e2:
            print(f"모든 모델 로드 실패: {e2}")
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
    """현재 리뷰 목록 저장 (URL 크롤링용)"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'reviews': list(known_reviews),
                'last_updated': datetime.now().isoformat(),
                'monitored_url': monitored_url
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
        
        result = sentiment_analyzer(review_text[:512])[0]
        
        print(f"🔍 모델 원본 결과: {result}")
        
        # nlptown 모델은 1 STAR, 2 STARS, 3 STARS, 4 STARS, 5 STARS 라벨 사용
        label = result['label']
        confidence = result['score']
        
        # 1-2성은 부정, 3성은 중성, 4-5성은 긍정으로 분류
        if label in ['1 STAR', '2 STARS']:
            is_negative = True
            korean_label = '부정적'
        elif label in ['4 STARS', '5 STARS']:
            is_negative = False
            korean_label = '긍정적'
        else:  # 3 STARS
            # 3성은 신뢰도에 따라 결정 (0.6 이상이면 중성, 미만이면 부정으로 처리)
            is_negative = confidence < 0.6
            korean_label = '부정적' if is_negative else '중성적'
        
        print(f"🎯 최종 분류: {korean_label} (is_negative={is_negative})")
        
        return {
            'is_negative': is_negative,
            'confidence': confidence,
            'label': korean_label,
            'score': round(confidence * 100, 2),
            'original_label': label
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

def monitoring_loop():
    """백그라운드에서 실행되는 모니터링 루프"""
    global monitoring_active, known_reviews
    
    while monitoring_active:
        try:
            print(f"모니터링 확인 중... ({datetime.now().strftime('%H:%M:%S')})")
            
            # 새로운 리뷰 크롤링 (최근 1페이지만)
            reviews = crawler.crawl_reviews(monitored_url)
            
            if not reviews:
                print("크롤링된 리뷰가 없습니다.")
                time.sleep(60)  # 1분 대기
                continue
            
            # 신규 리뷰 찾기
            new_reviews = []
            for review in reviews:
                review_key = review['text'].strip()
                if review_key not in known_reviews:
                    # 감정 분석
                    analysis = analyze_review(review['text'])
                    review.update(analysis)
                    new_reviews.append(review)
                    known_reviews.add(review_key)
            
            if new_reviews:
                # 부정 리뷰만 필터링
                negative_reviews = [r for r in new_reviews if r.get('is_negative', False)]
                
                # 알림 전송
                send_notification(new_reviews, negative_reviews)
                
                # 데이터 저장
                save_known_reviews()
            else:
                print("신규 리뷰가 없습니다.")
            
        except Exception as e:
            print(f"모니터링 오류: {e}")
        
        # 1시간 대기 (3600초)
        time.sleep(3600)

def cafe24_monitoring_loop():
    """카페24 API 기반 모니터링 루프 - 부정리뷰 탐지 중심"""
    global monitoring_active, known_reviews
    
    while monitoring_active:
        try:
            print(f"카페24 API 모니터링 확인 중... ({datetime.now().strftime('%H:%M:%S')})")
            
            # 카페24 API로 최신 리뷰 가져오기
            reviews = review_api.get_latest_reviews(limit=20)
            
            if not reviews:
                print("카페24 API에서 가져온 리뷰가 없습니다.")
                time.sleep(300)  # 5분 대기
                continue
            
            # 신규 리뷰 찾기 (article_no 기준)
            new_reviews = []
            for review in reviews:
                article_id = str(review.get('article_no', ''))
                if article_id not in known_reviews:
                    # 감정 분석 수행
                    if review.get('content'):
                        analyzed = analyzer.analyze_reviews_batch([{
                            'text': review['content'],
                            'title': review.get('title', ''),
                            'writer': review.get('writer', ''),
                            'product_no': review.get('product_no'),
                            'article_no': review.get('article_no'),
                            'created_date': review.get('created_date'),
                            'rating': review.get('rating', 0)
                        }])
                        
                        if analyzed:
                            review.update(analyzed[0])  # 분석 결과 병합
                            new_reviews.append(review)
                            known_reviews.add(article_id)
            
            if new_reviews:
                # 부정 리뷰만 필터링
                negative_reviews = [r for r in new_reviews if r.get('is_negative', False)]
                
                print(f"신규 리뷰 {len(new_reviews)}개 발견, 부정리뷰 {len(negative_reviews)}개")
                
                # 부정 리뷰가 있으면 우선적으로 알림
                if negative_reviews:
                    notification_manager.add_monitoring_notification(
                        'negative_found',
                        f"🚨 부정리뷰 {len(negative_reviews)}개 발견! (총 신규 리뷰 {len(new_reviews)}개)",
                        {
                            'type': 'cafe24',
                            'new_count': len(new_reviews),
                            'negative_count': len(negative_reviews),
                            'negative_reviews': [
                                {
                                    'content': r.get('content', ''),
                                    'score': r.get('score', 0),
                                    'product_no': r.get('product_no'),
                                    'writer': r.get('writer', ''),
                                    'created_date': r.get('created_date')
                                }
                                for r in negative_reviews[:3]  # 상위 3개만
                            ]
                        }
                    )
                else:
                    # 부정 리뷰가 없어도 신규 리뷰 알림
                    notification_manager.add_monitoring_notification(
                        'new_reviews',
                        f"📝 신규 리뷰 {len(new_reviews)}개 발견 (모두 긍정적)",
                        {
                            'type': 'cafe24',
                            'new_count': len(new_reviews),
                            'negative_count': 0
                        }
                    )
                
                # 데이터 저장
                save_known_reviews()
            else:
                print("카페24 API에서 신규 리뷰가 없습니다.")
            
        except Exception as e:
            print(f"카페24 모니터링 오류: {e}")
            # API 오류 시 토큰 갱신 시도
            if "401" in str(e) or "인증" in str(e):
                print("토큰 갱신 시도 중...")
                try:
                    oauth_client.refresh_tokens_if_needed()
                except:
                    pass
        
        # 30분 대기 (카페24 API는 더 자주 체크)
        time.sleep(1800)

# ===== 카페24 OAuth 관련 엔드포인트 =====

def init_oauth_client():
    """OAuth 클라이언트 초기화 (settings 사용)"""
    global oauth_client
    
    if settings.cafe24_client_id and settings.cafe24_client_secret and settings.cafe24_mall_id:
        try:
            oauth_client = Cafe24OAuth(
                client_id=settings.cafe24_client_id,
                client_secret=settings.cafe24_client_secret,
                mall_id=settings.cafe24_mall_id,
                redirect_uri=settings.redirect_uri
            )
            print(f"✅ OAuth 클라이언트 초기화 완료")
            print(f"   - Mall ID: {settings.cafe24_mall_id}")
            print(f"   - Client ID: {settings.cafe24_client_id}")
            print(f"   - Redirect URI: {settings.redirect_uri}")
            
        except Exception as e:
            print(f"❌ OAuth 클라이언트 초기화 실패: {e}")
    else:
        missing = []
        if not settings.cafe24_client_id:
            missing.append("CAFE24_CLIENT_ID")
        if not settings.cafe24_client_secret:
            missing.append("CAFE24_CLIENT_SECRET")
        if not settings.cafe24_mall_id:
            missing.append("CAFE24_MALL_ID")
        
        print(f"❌ OAuth 설정이 완료되지 않았습니다. 누락: {', '.join(missing)}")

@app.route('/auth/setup', methods=['GET', 'POST'])
def setup_auth():
    """카페24 API 설정"""
    if request.method == 'GET':
        # 현재 설정 상태 반환
        return jsonify({
            'configured': bool(settings.cafe24_client_id and settings.cafe24_client_secret),
            'mall_id': settings.cafe24_mall_id or '',
            'redirect_uri': settings.redirect_uri
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
        
        # settings에서 직접 URL 생성
        if not settings.cafe24_client_id or not settings.cafe24_mall_id:
            return jsonify({'error': '카페24 설정이 완료되지 않았습니다.'}), 400
        
        # 직접 OAuth URL 생성
        auth_url = f"https://{settings.cafe24_mall_id}.cafe24api.com/api/v2/oauth/authorize?" \
                  f"response_type=code&" \
                  f"client_id={settings.cafe24_client_id}&" \
                  f"redirect_uri={settings.redirect_uri}&" \
                  f"scope=mall.read_product,mall.read_category,mall.read_store,mall.read_community"
        
        print(f"✅ 인증 URL 생성 완료:")
        print(f"   - URL: {auth_url}")
        
        return jsonify({
            'auth_url': auth_url,
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
            return jsonify({'error': f'인증 오류: {error}'}), 400
        
        if not code:
            print(f"❌ 인증 코드가 없습니다.")
            return jsonify({'error': '인증 코드가 없습니다.'}), 400
        
        # state 검증 (개발 중에는 건너뛰기)
        # if state != session.get('oauth_state'):
        #     return jsonify({'error': '인증 상태가 유효하지 않습니다.'}), 400
        
        if not oauth_client:
            print(f"❌ OAuth 클라이언트가 없습니다.")
            return jsonify({'error': 'OAuth 클라이언트가 초기화되지 않았습니다.'}), 400
        
        print(f"🔐 액세스 토큰 발급 중...")
        # 액세스 토큰 발급
        token_data = oauth_client.get_access_token(code)
        print(f"✅ 토큰 발급 완료: {token_data}")
        
        # Review API 클라이언트 초기화
        global review_api
        review_api = Cafe24ReviewAPI(oauth_client)
        print(f"📝 Review API 클라이언트 초기화 완료")
        
        # 세션 정리
        session.pop('oauth_state', None)
        
        # 알림 추가
        notification_manager.add_system_notification(
            "카페24 OAuth 인증이 완료되었습니다.", "success"
        )
        
        print(f"🎉 OAuth 인증 성공!")
        
        return jsonify({
            'message': '카페24 OAuth 인증이 완료되었습니다.',
            'token_expires_at': token_data.get('expires_at'),
            'scopes': token_data.get('scopes', [])
        })
        
    except Exception as e:
        print(f"❌ OAuth 콜백 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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
@login_required
def get_review_boards():
    """리뷰 게시판 목록 조회"""
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        boards = review_api.get_review_boards()
        
        return jsonify({
            'boards': boards,
            'count': len(boards)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/latest')
@login_required
def get_latest_reviews():
    """최신 리뷰 조회"""
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        days = request.args.get('days', 7, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        reviews = review_api.get_latest_reviews(days=days, limit=limit)
        
        # 감정 분석 수행
        if reviews:
            analyzed_reviews = analyzer.analyze_reviews_batch(reviews)
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews)
            statistics = analyzer.get_review_statistics(enriched_reviews)
            negative_reviews = analyzer.get_negative_reviews(enriched_reviews)
            
            return jsonify({
                'reviews': enriched_reviews,
                'statistics': statistics,
                'negative_reviews': negative_reviews[:10],  # 상위 10개
                'count': len(enriched_reviews)
            })
        else:
            return jsonify({
                'reviews': [],
                'statistics': analyzer.get_review_statistics([]),
                'negative_reviews': [],
                'count': 0
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/product/<int:product_no>')
@login_required
def get_product_reviews(product_no):
    """특정 상품의 리뷰 조회"""
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        limit = request.args.get('limit', 100, type=int)
        
        reviews = review_api.get_product_reviews(product_no=product_no, limit=limit)
        
        if reviews:
            analyzed_reviews = analyzer.analyze_reviews_batch(reviews)
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews)
            statistics = analyzer.get_review_statistics(enriched_reviews)
            negative_reviews = analyzer.get_negative_reviews(enriched_reviews)
            
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
                'statistics': analyzer.get_review_statistics([]),
                'negative_reviews': [],
                'count': 0,
                'message': '해당 상품의 리뷰를 찾을 수 없습니다.'
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/search')
@login_required
def search_reviews():
    """리뷰 검색"""
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        keyword = request.args.get('keyword', '').strip()
        limit = request.args.get('limit', 50, type=int)
        
        if not keyword:
            return jsonify({'error': '검색 키워드를 입력해주세요.'}), 400
        
        reviews = review_api.search_reviews(keyword=keyword, limit=limit)
        
        if reviews:
            analyzed_reviews = analyzer.analyze_reviews_batch(reviews)
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews)
            statistics = analyzer.get_review_statistics(enriched_reviews)
            negative_reviews = analyzer.get_negative_reviews(enriched_reviews)
            
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
                'statistics': analyzer.get_review_statistics([]),
                'negative_reviews': [],
                'count': 0,
                'message': f"'{keyword}'에 대한 리뷰를 찾을 수 없습니다."
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products')
@login_required
def get_products():
    """상품 목록 조회"""
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
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
                'name': 'Administrator',
                'email': 'admin@example.com',
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

@app.route('/crawl_and_analyze', methods=['POST'])
@login_required
def crawl_and_analyze():
    """URL에서 리뷰를 크롤링하고 분석"""
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({'error': 'URL을 입력해주세요.'}), 400
        
        # 제품 정보 추출
        product_info = crawler.extract_product_info(url)
        
        # 리뷰 크롤링
        reviews = crawler.crawl_reviews(url)
        
        if not reviews:
            return jsonify({'error': '리뷰를 찾을 수 없습니다.'}), 404
        
        # 리뷰 분석 (analyzer 사용)
        analyzed_reviews = analyzer.analyze_reviews_batch(reviews)
        
        # 통계 계산
        statistics = analyzer.get_review_statistics(analyzed_reviews)
        negative_reviews = analyzer.get_negative_reviews(analyzed_reviews)
        positive_reviews = [r for r in analyzed_reviews if not r.get('is_negative', False)]
        
        response = {
            'product': product_info,
            'reviews': analyzed_reviews,
            'summary': statistics,
            'top_negative': negative_reviews[:5],  # 상위 5개 부정 리뷰
            'top_positive': positive_reviews[:5]   # 상위 5개 긍정 리뷰
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_monitoring', methods=['POST'])
@login_required
def start_monitoring():
    """모니터링 시작 (URL 기반)"""
    global monitoring_active, monitoring_thread, monitored_url
    
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({'error': 'URL을 입력해주세요.'}), 400
        
        if monitoring_active:
            return jsonify({'error': '이미 모니터링이 실행 중입니다.'}), 400
        
        # 모니터링 설정
        monitored_url = url
        monitoring_active = True
        
        # 기존 리뷰 데이터 로드
        load_known_reviews()
        
        # 초기 리뷰 수집 (기존 리뷰 등록)
        print("초기 리뷰 수집 중...")
        initial_reviews = crawler.crawl_reviews(url)
        for review in initial_reviews:
            known_reviews.add(review['text'].strip())
        
        save_known_reviews()
        print(f"초기 리뷰 {len(initial_reviews)}개 등록 완료")
        
        # 모니터링 스레드 시작
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
        
        # 알림 추가
        notification_manager.add_monitoring_notification(
            'started', 
            f"URL 모니터링이 시작되었습니다: {url}",
            {'url': url, 'initial_reviews': len(initial_reviews)}
        )
        
        return jsonify({
            'message': '모니터링이 시작되었습니다.',
            'url': url,
            'initial_reviews': len(initial_reviews)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_cafe24_monitoring', methods=['POST'])
@login_required
def start_cafe24_monitoring():
    """카페24 API 기반 모니터링 시작"""
    global monitoring_active, monitoring_thread, monitored_url
    
    try:
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        if monitoring_active:
            return jsonify({'error': '이미 모니터링이 실행 중입니다.'}), 400
        
        # 카페24 API 기반 모니터링 설정
        monitored_url = "CAFE24_API"  # API 기반 모니터링 표시
        monitoring_active = True
        
        # 기존 리뷰 데이터 로드
        load_known_reviews()
        
        # 초기 리뷰 수집 (카페24 API로)
        print("카페24 API에서 초기 리뷰 수집 중...")
        initial_reviews = review_api.get_latest_reviews(limit=50)
        
        # 기존 리뷰 ID 저장 (API 기반이므로 article_no 사용)
        for review in initial_reviews:
            known_reviews.add(str(review.get('article_no', '')))
        
        save_known_reviews()
        print(f"초기 리뷰 {len(initial_reviews)}개 등록 완료")
        
        # 모니터링 스레드 시작 (카페24 API 기반)
        monitoring_thread = threading.Thread(target=cafe24_monitoring_loop, daemon=True)
        monitoring_thread.start()
        
        # 알림 추가
        notification_manager.add_monitoring_notification(
            'started', 
            f"카페24 API 모니터링이 시작되었습니다",
            {'type': 'cafe24', 'initial_reviews': len(initial_reviews)}
        )
        
        return jsonify({
            'message': '카페24 API 기반 모니터링이 시작되었습니다.',
            'type': 'cafe24',
            'initial_reviews': len(initial_reviews)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
        # 모니터링 설정
        monitored_url = url
        monitoring_active = True
        
        # 기존 리뷰 데이터 로드
        load_known_reviews()
        
        # 초기 리뷰 수집 (기존 리뷰 등록)
        print("초기 리뷰 수집 중...")
        initial_reviews = crawler.crawl_reviews(url)
        for review in initial_reviews:
            known_reviews.add(review['text'].strip())
        
        save_known_reviews()
        print(f"초기 리뷰 {len(initial_reviews)}개 등록 완료")
        
        # 모니터링 스레드 시작
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
        
        # 알림 추가
        notification_manager.add_monitoring_notification(
            'started', 
            f"URL 모니터링이 시작되었습니다: {url}",
            {'url': url, 'initial_reviews': len(initial_reviews)}
        )
        
        return jsonify({
            'message': '모니터링이 시작되었습니다.',
            'url': url,
            'initial_reviews': len(initial_reviews)
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
        'url': monitored_url,
        'known_reviews_count': len(known_reviews)
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
            'cafe24': config.get_cafe24_config(),
            'analysis': config.get_analysis_config(),
            'monitoring': config.get_monitoring_config(),
            'app': config.get_app_config(),
            'configured': config.is_cafe24_configured()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("서버 시작 중...")
    
    # 감정 분석 모델 로드
    load_model()
    
    # 설정 상태 출력
    print("=== 설정 상태 ===")
    print(f"카페24 Mall ID: {settings.cafe24_mall_id}")
    print(f"카페24 Access Token: {'설정됨' if settings.cafe24_access_token else '미설정'}")
    print(f"카페24 Refresh Token: {'설정됨' if settings.cafe24_refresh_token else '미설정'}")
    print(f"웹훅 이벤트 키: {'설정됨' if settings.WEBHOOK_EVENT_KEY else '미설정'}")
    print(f"서비스 키: {'설정됨' if settings.SERVICE_KEY else '미설정'}")
    print()
    
    # 카페24 OAuth 클라이언트 초기화
    init_oauth_client()
    
    # 카페24 API 클라이언트 초기화 (직접 토큰 사용)
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
    
    # 앱 실행 (AirPlay 피하기 위해 포트 5001 사용)
    app.run(
        debug=True, 
        port=5001,
        host='0.0.0.0'
    )