from flask import Blueprint, request, jsonify, session, render_template
from datetime import datetime
from app.shared.utils.notification import notification_manager
from config.settings import settings
from app.infrastructure.auth.cafe24_oauth import Cafe24OAuth
from app.infrastructure.external.cafe24.cafe24_reviews import Cafe24ReviewAPI

oauth_bp = Blueprint('oauth', __name__, url_prefix='/auth')

def get_app_globals():
    """app.py의 전역 변수들에 접근"""
    from flask import current_app
    return current_app.config.get('app_globals', {})

def get_or_create_oauth_client():
    """OAuth 클라이언트를 lazy하게 초기화하여 반환"""
    app_globals = get_app_globals()
    oauth_client = app_globals.get('oauth_client')
    
    if not oauth_client:
        try:
            oauth_client = Cafe24OAuth(
                client_id=settings.cafe24_client_id,
                client_secret=settings.cafe24_client_secret,
                mall_id=settings.cafe24_id,
                redirect_uri=settings.cafe24_redirect_uri
            )
            app_globals['oauth_client'] = oauth_client
            print("✅ OAuth 클라이언트 lazy 초기화 완료")
        except Exception as e:
            print(f"❌ OAuth 클라이언트 초기화 실패: {e}")
            return None
    
    return oauth_client

def init_oauth_client():
    """OAuth 클라이언트 초기화"""
    try:
        oauth_client = Cafe24OAuth(
            client_id=settings.cafe24_client_id,
            client_secret=settings.cafe24_client_secret,
            mall_id=settings.cafe24_id,
            redirect_uri=settings.cafe24_redirect_uri
        )
        
        app_globals = get_app_globals()
        app_globals['oauth_client'] = oauth_client
        
        print("✅ OAuth 클라이언트 초기화 완료")
        return oauth_client
        
    except Exception as e:
        print(f"❌ OAuth 클라이언트 초기화 실패: {e}")
        raise e

# ===== 카페24 OAuth 관련 엔드포인트 =====

@oauth_bp.route('/setup', methods=['GET', 'POST'])
def setup_auth():
    """카페24 API 설정"""
    if request.method == 'GET':
        # 현재 설정 상태 반환 (디버그 정보 포함)
        app_globals = get_app_globals()
        oauth_client = app_globals.get('oauth_client')
        
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

@oauth_bp.route('/start')
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

@oauth_bp.route('/process_callback', methods=['POST'])
def process_callback():
    """외부에서 전달받은 OAuth 콜백 처리"""
    try:
        data = request.json
        code = data.get('code')
        state = data.get('state')
        
        if not code:
            return jsonify({'error': '인증 코드가 없습니다.'}), 400
        
        app_globals = get_app_globals()
        oauth_client = app_globals.get('oauth_client')
        
        if not oauth_client:
            return jsonify({'error': 'OAuth 클라이언트가 초기화되지 않았습니다.'}), 400
        
        # 액세스 토큰 발급
        token_data = oauth_client.get_access_token(code)
        
        # Review API 클라이언트 초기화
        review_api = Cafe24ReviewAPI(oauth_client)
        app_globals['review_api'] = review_api
        
        # 리뷰 캐시 초기화 - app.py 함수 호출
        from flask import current_app
        initialize_review_cache = current_app.config.get('initialize_review_cache')
        cached_reviews = current_app.config.get('cached_reviews')
        
        if initialize_review_cache and not cached_reviews:
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

@oauth_bp.route('/callback')
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
        app_globals = get_app_globals()
        review_api = Cafe24ReviewAPI(client)
        app_globals['review_api'] = review_api
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

# ===== OAuth 토큰 상태 및 관리 엔드포인트 =====

@oauth_bp.route('/status')
def auth_status():
    """인증 상태 확인"""
    try:
        app_globals = get_app_globals()
        oauth_client = app_globals.get('oauth_client')
        
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

@oauth_bp.route('/manual_token', methods=['POST'])
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
        
        app_globals = get_app_globals()
        oauth_client = app_globals.get('oauth_client')
        
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
        review_api = Cafe24ReviewAPI(oauth_client)
        app_globals['review_api'] = review_api
        
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

@oauth_bp.route('/revoke', methods=['POST'])
def revoke_token():
    """토큰 폐기"""
    try:
        app_globals = get_app_globals()
        oauth_client = app_globals.get('oauth_client')
        
        if not oauth_client:
            return jsonify({'error': 'OAuth 클라이언트가 초기화되지 않았습니다.'}), 400
        
        result = oauth_client.revoke_token()
        
        if result:
            # Review API 클라이언트 제거
            app_globals['review_api'] = None
            
            notification_manager.add_system_notification(
                "카페24 API 토큰이 폐기되었습니다.", "warning"
            )
            
            return jsonify({'message': '토큰이 성공적으로 폐기되었습니다.'})
        else:
            return jsonify({'error': '토큰 폐기에 실패했습니다.'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500