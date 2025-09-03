import requests
import json
import csv
import pandas as pd
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

class Cafe24ReviewScraper:
    def __init__(self, api_key: str, access_token: str):
        """
        카페24 API를 사용한 상품리뷰 수집기
        """
        self.mall_id = mall_id
        self.access_token = access_token
        self.base_url = "https://api.cafe24.com/api/v2/admin"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Cafe24-Api-Version": "2025-06-01"
        }

    def get_boards(self) -> List[Dict]:
