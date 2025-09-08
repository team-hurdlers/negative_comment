from functools import wraps
from flask import session, jsonify

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
        from flask import current_app
        app_globals = current_app.config.get('app_globals', {})
        review_api = app_globals.get('review_api')
        
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def full_auth_required(f):
    """사용자 로그인 + 카페24 API 인증 둘 다 필요한 엔드포인트 (프론트엔드 API용)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import current_app
        
        # 먼저 사용자 로그인 체크
        if 'user' not in session:
            return jsonify({'error': '로그인이 필요합니다.', 'login_required': True}), 401
        
        # 그 다음 카페24 API 토큰 체크
        app_globals = current_app.config.get('app_globals', {})
        review_api = app_globals.get('review_api')
        
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.', 'cafe24_auth_required': True}), 401
        
        return f(*args, **kwargs)
    return decorated_function