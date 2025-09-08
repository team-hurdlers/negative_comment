from flask import Blueprint, request, jsonify
from app.shared.middlewares.auth import login_required
from config.settings import settings

monitoring_bp = Blueprint('monitoring', __name__)

def get_app_globals():
    """app.py의 전역 변수들에 접근"""
    from flask import current_app
    return current_app.config.get('app_globals', {})

@monitoring_bp.route('/webhook/init', methods=['POST'])
@login_required
def init_webhook_system():
    """웹훅 기반 시스템 초기화"""
    try:
        from flask import current_app
        
        app_globals = get_app_globals()
        review_api = app_globals.get('review_api')
        review_service = current_app.config.get('review_service')
        notification_manager = current_app.config.get('notification_manager')
        
        # 필요한 함수들 가져오기
        load_known_reviews = current_app.config.get('load_known_reviews')
        initialize_review_cache = current_app.config.get('initialize_review_cache')
        
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        
        # 웹훅 시스템 활성화
        current_app.config['monitoring_active'] = True
        
        # 기존 리뷰 데이터 로드
        if load_known_reviews:
            load_known_reviews()
        
        # 리뷰 캐시 초기화
        if not review_service.cached_reviews:
            print("리뷰 캐시 초기화 중...")
            if initialize_review_cache:
                initialize_review_cache()
        
        # 알림 추가
        if notification_manager:
            notification_manager.add_monitoring_notification(
                'webhook_ready', 
                "웹훅 기반 리뷰 모니터링 시스템이 준비되었습니다",
                {'type': 'webhook_system', 'cached_reviews': len(review_service.cached_reviews)}
            )
        
        return jsonify({
            'message': '웹훅 기반 리뷰 모니터링 시스템이 준비되었습니다.',
            'type': 'webhook',
            'cached_reviews': len(review_service.cached_reviews),
            'webhook_enabled': True
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitoring_bp.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """모니터링 정지"""
    try:
        from flask import current_app
        
        monitoring_active = current_app.config.get('monitoring_active', False)
        
        if not monitoring_active:
            return jsonify({'error': '모니터링이 실행 중이지 않습니다.'}), 400
        
        current_app.config['monitoring_active'] = False
        
        # 알림 추가
        notification_manager = current_app.config.get('notification_manager')
        if notification_manager:
            notification_manager.add_monitoring_notification(
                'stopped', 
                "리뷰 모니터링이 정지되었습니다."
            )
        
        return jsonify({
            'message': '모니터링이 정지되었습니다.'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@monitoring_bp.route('/monitoring_status')
def monitoring_status():
    """모니터링 상태 확인"""
    try:
        from flask import current_app
        
        monitoring_active = current_app.config.get('monitoring_active', False)
        review_service = current_app.config.get('review_service')
        
        return jsonify({
            'active': monitoring_active,
            'type': 'webhook_based',
            'known_reviews_count': len(review_service.known_reviews) if review_service else 0,
            'cached_reviews_count': len(review_service.cached_reviews) if review_service else 0,
            'webhook_enabled': True,
            'webhook_event_key_configured': bool(settings.WEBHOOK_EVENT_KEY)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500