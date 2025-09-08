from flask import Blueprint, request, jsonify, session
from app.shared.utils.notification import notification_manager
from config.settings import settings

auth_bp = Blueprint('auth', __name__)

def verify_credentials(username, password):
    """사용자 인증 확인"""
    return username == settings.cafe24_id and password == settings.cafe24_password

# ===== 로그인 엔드포인트 =====

@auth_bp.route('/login', methods=['POST'])
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

@auth_bp.route('/logout', methods=['POST'])
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

@auth_bp.route('/user/status')
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

# ===== 채널톡/카카오 인증 상태 및 테스트 엔드포인트 =====

@auth_bp.route('/channel-talk/status')
def channel_talk_auth_status():
    """채널톡 인증 상태 확인"""
    try:
        # 채널톡 액세스 토큰과 시크릿이 설정되어 있으면 인증 완료
        access_token_configured = bool(notification_manager.channel_talk_access_token)
        secret_configured = bool(notification_manager.channel_talk_secret)
        
        authenticated = access_token_configured and secret_configured
        
        print(f"🔍 채널톡 상태 확인:")
        print(f"   액세스 토큰: {'설정됨' if access_token_configured else '미설정'}")
        print(f"   시크릿 키: {'설정됨' if secret_configured else '미설정'}")
        print(f"   인증 상태: {'완료' if authenticated else '미완료'}")
        
        return jsonify({
            'authenticated': authenticated,
            'access_token_configured': access_token_configured,
            'secret_configured': secret_configured,
            'message': '채널톡 인증 완료' if authenticated else '채널톡 인증 필요'
        })
        
    except Exception as e:
        print(f"❌ 채널톡 인증 상태 확인 실패: {e}")
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/test/kakao-notification', methods=['POST'])
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

@auth_bp.route('/test/channel-talk-notification', methods=['POST'])
def test_channel_talk_notification():
    """채널톡 알림 테스트"""
    try:
        data = request.json or {}
        message = data.get('message', '채널톡 알림 테스트 메시지입니다! 🎉')
        channel_id = data.get('channel_id')
        
        print(f"🔍 채널톡 테스트 메시지 전송 시도: {message[:50]}...")
        print(f"🔍 액세스 토큰 상태: {'있음' if notification_manager.channel_talk_access_token else '없음'}")
        print(f"🔍 시크릿 키 상태: {'있음' if notification_manager.channel_talk_secret else '없음'}")
        
        # 액세스 토큰이나 시크릿이 없으면 구체적인 오류 메시지 반환
        if not notification_manager.channel_talk_access_token or not notification_manager.channel_talk_secret:
            print("❌ 채널톡 인증 정보가 없습니다.")
            return jsonify({'error': '채널톡 인증이 필요합니다. 먼저 채널톡 토큰을 설정해주세요.'}), 400
        
        success = notification_manager.send_channel_talk_message(message, channel_id)
        
        if success:
            print("✅ 채널톡 테스트 메시지 전송 성공")
            return jsonify({
                'message': '채널톡 테스트 메시지가 전송되었습니다.',
                'success': True
            })
        else:
            print("❌ 채널톡 메시지 전송 실패 - send_channel_talk_message returned False")
            return jsonify({'error': '채널톡 메시지 전송에 실패했습니다. 토큰이 잘못되었거나 API 오류가 발생했습니다.'}), 400
            
    except Exception as e:
        print(f"❌ 채널톡 테스트 메시지 전송 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'서버 오류: {str(e)}'}), 500