import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        # Cafe24 API 설정
        self.cafe24_client_id = os.getenv("CAFE24_CLIENT_ID")
        self.cafe24_client_secret = os.getenv("CAFE24_CLIENT_SECRET")
        self.cafe24_id = os.getenv("CAFE24_ID")
        self.cafe24_password = os.getenv("CAFE24_PASSWORD")
        self.cafe24_redirect_uri = os.getenv("CAFE24_REDIRECT_URI")

        # API Keys
        self.SERVICE_KEY = os.getenv("SERVICE_KEY")
        self.WEBHOOK_EVENT_KEY = os.getenv("WEBHOOK_EVENT_KEY")
        self.kakao_api_key = os.getenv("KAKAO_API_KEY")
        self.kakao_access_token = os.getenv("KAKAO_ACCESS_TOKEN")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        # Channel Talk 설정
        self.channel_talk_access_key = os.getenv("CHANNEL_TALK_ACCESS_TOKEN")
        self.channel_talk_secret_key = os.getenv("CHANNEL_TALK_SECRET")
        self.channel_talk_group_id = os.getenv("CHANNEL_TALK_GROUP_ID")

        
        # 모니터링 설정
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "300"))
        self.max_reviews_per_check = int(os.getenv("MAX_REVIEWS_PER_CHECK", "50"))
        self.notification_enabled = os.getenv("NOTIFICATION_ENABLED", "false").lower() == "true"
        self.notification_method = os.getenv("NOTIFICATION_METHOD", "both")  # kakao, channel_talk, both
        
        # 앱 설정
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.port = int(os.getenv("PORT", "5001"))
        self.host = os.getenv("HOST", "0.0.0.0")


settings = Settings()