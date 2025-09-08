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