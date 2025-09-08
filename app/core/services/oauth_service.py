from app.infrastructure.auth.cafe24_oauth import Cafe24OAuth
from config.settings import settings

class OAuthService:
    def __init__(self):
        self.oauth_client = None
    
    def get_or_create_oauth_client(self):
        """OAuth 클라이언트를 lazy하게 초기화하여 반환"""
        # 이미 초기화된 경우 기존 클라이언트 반환
        if self.oauth_client is not None:
            return self.oauth_client
        
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
            self.oauth_client = Cafe24OAuth(
                client_id=settings.cafe24_client_id,
                client_secret=settings.cafe24_client_secret,
                mall_id=settings.cafe24_id,
                redirect_uri=settings.cafe24_redirect_uri
            )
            print(f"✅ OAuth 클라이언트 lazy 초기화 완료")
            print(f"   - Mall ID: {settings.cafe24_id}")
            print(f"   - Client ID: {settings.cafe24_client_id}")
            print(f"   - Redirect URI: {settings.cafe24_redirect_uri}")
            return self.oauth_client
            
        except Exception as e:
            print(f"❌ OAuth 클라이언트 초기화 실패: {e}")
            return None

    def init_oauth_client(self):
        """기존 코드 호환성을 위한 wrapper 함수"""
        return self.get_or_create_oauth_client()