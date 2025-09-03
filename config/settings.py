import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.cafe24_client_id = os.getenv("CAFE24_CLIENT_ID")
        self.cafe24_client_secret = os.getenv("CAFE24_CLIENT_SECRET")
        self.SERVICE_KEY = os.getenv("SERVICE_KEY")
        self.WEBHOOK_EVENT_KEY = int(os.getenv("WEBHOOK_EVENT_KEY"))
        self.cafe24_id = os.getenv("CAFE24_ID")
        self.cafe24_password = os.getenv("CAFE24_PASSWORD")
settings = Settings()