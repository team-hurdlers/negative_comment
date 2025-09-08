from flask import Flask, request, jsonify, render_template, redirect, session, url_for
from flask_cors import CORS
from app.infrastructure.auth.cafe24_oauth import Cafe24OAuth
from app.infrastructure.external.cafe24.cafe24_reviews import Cafe24ReviewAPI
from app.infrastructure.external.openai.review_analyzer import ReviewAnalyzer
from app.shared.utils.notification import NotificationManager
from app.api.v1.auth import auth_bp
from app.api.v1.webhook import webhook_bp
from app.api.v1.oauth import oauth_bp
from app.api.v1.reviews import reviews_bp
from app.api.v1.monitoring import monitoring_bp
from app.api.v1.notifications import notifications_bp
from app.api.v1.config import config_bp
from app.api.v1.main import main_bp
from app.core.services.review_service import ReviewService
from app.core.services.webhook_service import WebhookService
from app.core.services.alert_service import AlertService
from app.core.services.cafe24_service import Cafe24Service
from app.core.services.oauth_service import OAuthService
from app.shared.utils.auth_utils import verify_credentials as auth_verify_credentials, verify_webhook_event_key as auth_verify_webhook_event_key
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

# Blueprint 등록
app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(oauth_bp)
app.register_blueprint(reviews_bp)
app.register_blueprint(monitoring_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(config_bp)

# 설정 및 관리자 초기화
notification_manager = NotificationManager()
review_service = ReviewService(notification_manager)
webhook_service = WebhookService(notification_manager)
alert_service = AlertService(notification_manager)
cafe24_service = Cafe24Service()
oauth_service = OAuthService()

# OAuth 클라이언트와 Review API를 위한 전역 변수
oauth_client = None
review_api = None

# ReviewService 관련 함수들을 전역 함수로 위임 (기존 코드 호환성 유지)
def load_model():
    return review_service.load_model()

def load_known_reviews():
    return review_service.load_known_reviews()

def save_known_reviews():
    return review_service.save_known_reviews()

def load_review_cache():
    return review_service.load_review_cache()

def save_review_cache():
    return review_service.save_review_cache()

def initialize_review_cache():
    return review_service.initialize_review_cache(review_api)

def find_new_reviews():
    return review_service.find_new_reviews(review_api)

def analyze_review(review_text, rating=None):
    return review_service.analyze_review(review_text, rating)

def send_notification(new_reviews, negative_reviews):
    return review_service.send_notification(new_reviews, negative_reviews)

def send_negative_review_alert(content, analysis_result):
    return alert_service.send_negative_review_alert(content, analysis_result)

def trigger_review_collection():
    return alert_service.trigger_review_collection(review_api, find_new_reviews, analyze_reviews_batch, settings)

def enrich_reviews_with_product_names(reviews):
    return cafe24_service.enrich_reviews_with_product_names(reviews, review_api)

def extract_content_from_webhook(webhook_data):
    return webhook_service.extract_content_from_webhook(webhook_data)

def init_cafe24_client():
    global review_api
    review_api = cafe24_service.init_cafe24_client(oauth_client)
    return review_api

def process_cafe24_webhook(webhook_data):
    return webhook_service.process_cafe24_webhook(webhook_data, oauth_client, review_api, trigger_review_collection)

def extract_content_from_cafe24_webhook(webhook_data):
    return webhook_service.extract_content_from_cafe24_webhook(webhook_data)

def process_channel_talk_webhook(webhook_data):
    return webhook_service.process_channel_talk_webhook(webhook_data, analyze_review, send_negative_review_alert, trigger_review_collection, review_api)

# 모니터링 관련 변수만 유지 (Blueprint에서 필요)
monitoring_active = False
monitoring_thread = None

# 채널톡 웹훅 설정
WEBHOOK_EVENT_KEY = settings.WEBHOOK_EVENT_KEY
WEBHOOK_ENABLED = True

# OAuth 관련 함수
def get_or_create_oauth_client():
    global oauth_client
    oauth_client = oauth_service.get_or_create_oauth_client()
    return oauth_client

init_oauth_client = get_or_create_oauth_client

# 리뷰 분석 함수들 직접 참조
analyze_reviews_batch = review_service.analyze_reviews_batch
get_review_statistics = review_service.get_review_statistics
get_negative_reviews = review_service.get_negative_reviews

# auth_utils에서 import한 함수 사용
verify_credentials = auth_verify_credentials
verify_webhook_event_key = lambda event_key: auth_verify_webhook_event_key(event_key, WEBHOOK_EVENT_KEY)

# 리뷰 캐시 참조
cached_reviews = review_service.cached_reviews



# Blueprint에서 필요한 것들만 app.config에 등록
app.config.update({
    'oauth_client': oauth_client,
    'review_api': review_api,
    'trigger_review_collection': trigger_review_collection,
    'analyze_review': analyze_review,
    'send_negative_review_alert': send_negative_review_alert,
    'initialize_review_cache': initialize_review_cache,
    'cached_reviews': cached_reviews,
    'analyze_reviews_batch': analyze_reviews_batch,
    'enrich_reviews_with_product_names': enrich_reviews_with_product_names,
    'get_review_statistics': get_review_statistics,
    'get_negative_reviews': get_negative_reviews,
    'review_service': review_service,
    'webhook_service': webhook_service,
    'alert_service': alert_service,
    'cafe24_service': cafe24_service,
    'notification_manager': notification_manager,
    'monitoring_active': monitoring_active
})

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