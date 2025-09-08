from config.settings import settings

def verify_credentials(username, password):
    """사용자 인증 확인"""
    return username == settings.cafe24_id and password == settings.cafe24_password

def verify_webhook_event_key(event_key, webhook_event_key):
    """채널톡 웹훅 이벤트 키 검증"""
    try:
        if not webhook_event_key:
            print("WEBHOOK_EVENT_KEY가 설정되지 않았습니다.")
            return False
        return event_key == webhook_event_key
    except Exception as e:
        print(f"웹훅 이벤트 키 검증 오류: {e}")
        return False