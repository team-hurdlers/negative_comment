import requests
import base64
import json
import os
from urllib.parse import urlencode, parse_qs, urlparse
from datetime import datetime, timedelta
import secrets

class Cafe24OAuth:
    """카페24 OAuth 인증 관리 클래스"""
    
    def __init__(self, client_id: str, client_secret: str, mall_id: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.mall_id = mall_id
        self.redirect_uri = redirect_uri
        self.base_url = f"https://{mall_id}.cafe24api.com/api/v2"
        self.token_file = f"cafe24_tokens_{mall_id}.json"
        
    def get_authorization_url(self, scope: str = "mall.read_product,mall.read_category") -> tuple:
        """
        인증 URL 생성
        Returns: (authorization_url, state)
        """
        state = secrets.token_urlsafe(32)
        
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'state': state,
            'redirect_uri': self.redirect_uri,
            'scope': scope
        }
        
        auth_url = f"{self.base_url}/oauth/authorize?" + urlencode(params)
        return auth_url, state
    
    def get_access_token(self, authorization_code: str) -> dict:
        """
        인증 코드로 액세스 토큰 발급
        """
        url = f"{self.base_url}/oauth/token"
        
        # Basic Auth 헤더 생성
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': self.redirect_uri
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            
            # 토큰에 만료 시간 추가
            token_data['expires_in_seconds'] = 7200  # 2시간
            token_data['issued_at'] = datetime.now().isoformat()
            
            # 토큰 저장
            self.save_tokens(token_data)
            
            return token_data
            
        except requests.exceptions.RequestException as e:
            print(f"토큰 발급 실패: {e}")
            if hasattr(e.response, 'text'):
                print(f"응답 내용: {e.response.text}")
            raise
    
    def refresh_access_token(self, refresh_token: str = None) -> dict:
        """
        리프레시 토큰으로 액세스 토큰 갱신
        """
        if not refresh_token:
            # 저장된 토큰에서 리프레시 토큰 가져오기
            saved_tokens = self.load_tokens()
            if not saved_tokens or 'refresh_token' not in saved_tokens:
                raise ValueError("리프레시 토큰이 없습니다.")
            refresh_token = saved_tokens['refresh_token']
        
        url = f"{self.base_url}/oauth/token"
        
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            
            # 토큰에 만료 시간 추가
            token_data['expires_in_seconds'] = 7200  # 2시간
            token_data['issued_at'] = datetime.now().isoformat()
            
            # 토큰 저장
            self.save_tokens(token_data)
            
            return token_data
            
        except requests.exceptions.RequestException as e:
            print(f"토큰 갱신 실패: {e}")
            if hasattr(e.response, 'text'):
                print(f"응답 내용: {e.response.text}")
            raise
    
    def revoke_token(self, token: str = None) -> bool:
        """
        토큰 폐기
        """
        if not token:
            saved_tokens = self.load_tokens()
            if not saved_tokens or 'access_token' not in saved_tokens:
                raise ValueError("액세스 토큰이 없습니다.")
            token = saved_tokens['access_token']
        
        url = f"{self.base_url}/oauth/revoke"
        
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'token': token
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            
            # 저장된 토큰 파일 삭제
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
                
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"토큰 폐기 실패: {e}")
            return False
    
    def get_valid_token(self) -> str:
        """
        유효한 액세스 토큰 반환 (필요시 자동 갱신)
        """
        saved_tokens = self.load_tokens()
        
        if not saved_tokens or 'access_token' not in saved_tokens:
            raise ValueError("저장된 토큰이 없습니다. 인증을 다시 진행해주세요.")
        
        # 토큰 만료 확인
        if self.is_token_expired(saved_tokens):
            print("토큰이 만료되었습니다. 자동 갱신을 시도합니다.")
            try:
                new_tokens = self.refresh_access_token()
                return new_tokens['access_token']
            except Exception as e:
                print(f"토큰 자동 갱신 실패: {e}")
                raise ValueError("토큰 갱신에 실패했습니다. 인증을 다시 진행해주세요.")
        
        return saved_tokens['access_token']
    
    def is_token_expired(self, token_data: dict) -> bool:
        """
        토큰 만료 여부 확인
        """
        if 'issued_at' not in token_data or 'expires_in_seconds' not in token_data:
            return True
        
        issued_time = datetime.fromisoformat(token_data['issued_at'])
        expires_in = token_data['expires_in_seconds']
        expiry_time = issued_time + timedelta(seconds=expires_in)
        
        # 만료 5분 전부터 만료된 것으로 처리
        return datetime.now() >= (expiry_time - timedelta(minutes=5))
    
    def save_tokens(self, token_data: dict):
        """
        토큰을 파일에 저장
        """
        try:
            with open(self.token_file, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, ensure_ascii=False, indent=2)
            print(f"토큰이 {self.token_file}에 저장되었습니다.")
        except Exception as e:
            print(f"토큰 저장 실패: {e}")
    
    def load_tokens(self) -> dict:
        """
        파일에서 토큰 로드
        """
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"토큰 로드 실패: {e}")
        return {}
    
    def get_token_status(self) -> dict:
        """
        현재 토큰 상태 반환
        """
        saved_tokens = self.load_tokens()
        
        if not saved_tokens:
            return {
                'has_token': False,
                'status': 'no_token',
                'message': '저장된 토큰이 없습니다.'
            }
        
        is_expired = self.is_token_expired(saved_tokens)
        
        return {
            'has_token': True,
            'is_expired': is_expired,
            'status': 'expired' if is_expired else 'valid',
            'issued_at': saved_tokens.get('issued_at'),
            'expires_at': saved_tokens.get('expires_at'),
            'scopes': saved_tokens.get('scopes', []),
            'message': '토큰이 만료되었습니다.' if is_expired else '유효한 토큰입니다.'
        }


class Cafe24API:
    """카페24 API 클라이언트"""
    
    def __init__(self, oauth: Cafe24OAuth):
        self.oauth = oauth
        self.base_url = oauth.base_url
        
    def _get_headers(self) -> dict:
        """API 호출용 헤더 생성"""
        token = self.oauth.get_valid_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-Cafe24-Api-Version': '2025-06-01'
        }
    
    def get_products(self, **params) -> dict:
        """
        상품 목록 조회
        
        Args:
            limit: 조회할 상품 수 (기본: 10, 최대: 100)
            offset: 시작 위치 (기본: 0)
            product_no: 특정 상품 번호들 (콤마로 구분)
            fields: 조회할 필드들 (콤마로 구분)
            embed: 포함할 하위 리소스 (콤마로 구분)
            **params: 기타 필터 조건들
        """
        url = f"{self.base_url}/admin/products"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"상품 조회 실패: {e}")
            raise
    
    def get_product(self, product_no: int, **params) -> dict:
        """
        특정 상품 상세 조회
        """
        url = f"{self.base_url}/admin/products/{product_no}"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"상품 상세 조회 실패: {e}")
            raise
    
    def get_categories(self, **params) -> dict:
        """
        카테고리 목록 조회
        """
        url = f"{self.base_url}/admin/categories"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"카테고리 조회 실패: {e}")
            raise
    
    def get_boards(self, **params) -> dict:
        """
        게시판 목록 조회 (리뷰 게시판 포함)
        """
        url = f"{self.base_url}/admin/boards"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"게시판 조회 실패: {e}")
            raise
    
    def get_board_articles(self, board_no: int, **params) -> dict:
        """
        특정 게시판의 게시글 목록 조회
        """
        url = f"{self.base_url}/admin/boards/{board_no}/articles"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"게시글 조회 실패: {e}")
            raise


# 사용 예시 함수들
def setup_oauth():
    """OAuth 설정 예시"""
    # 카페24 개발자센터에서 발급받은 정보 입력
    CLIENT_ID = "your_client_id_here"
    CLIENT_SECRET = "your_client_secret_here"
    MALL_ID = "cila01"  # 쇼핑몰 ID
    REDIRECT_URI = "http://localhost:5000/callback"  # 개발자센터에 등록한 Redirect URL
    
    oauth = Cafe24OAuth(CLIENT_ID, CLIENT_SECRET, MALL_ID, REDIRECT_URI)
    return oauth

def start_authorization():
    """인증 시작"""
    oauth = setup_oauth()
    
    # 인증 URL 생성
    auth_url, state = oauth.get_authorization_url(
        scope="mall.read_product,mall.read_category,mall.read_store"
    )
    
    print("1. 다음 URL을 브라우저에서 열어 인증을 진행하세요:")
    print(auth_url)
    print("\n2. 인증 완료 후 리다이렉트된 URL에서 'code' 파라미터를 복사하세요.")
    print(f"3. state 값 확인: {state}")
    
    return oauth, state

def complete_authorization(oauth, authorization_code):
    """인증 완료"""
    try:
        token_data = oauth.get_access_token(authorization_code)
        print("토큰 발급 성공!")
        print(f"액세스 토큰: {token_data['access_token'][:20]}...")
        print(f"만료 시간: {token_data['expires_at']}")
        return token_data
    except Exception as e:
        print(f"토큰 발급 실패: {e}")
        return None

def test_api():
    """API 테스트"""
    oauth = setup_oauth()
    api = Cafe24API(oauth)
    
    try:
        # 토큰 상태 확인
        status = oauth.get_token_status()
        print(f"토큰 상태: {status}")
        
        if status['status'] != 'valid':
            print("유효한 토큰이 없습니다. 인증을 먼저 진행해주세요.")
            return
        
        # 상품 목록 조회 테스트
        print("\n=== 상품 목록 조회 ===")
        products = api.get_products(limit=5)
        print(f"조회된 상품 수: {len(products.get('products', []))}")
        
        # 카테고리 목록 조회 테스트
        print("\n=== 카테고리 목록 조회 ===")
        categories = api.get_categories(limit=5)
        print(f"조회된 카테고리 수: {len(categories.get('categories', []))}")
        
    except Exception as e:
        print(f"API 테스트 실패: {e}")

if __name__ == "__main__":
    # 사용법 안내
    print("카페24 OAuth 인증 및 API 사용법:")
    print("1. setup_oauth()로 OAuth 객체 생성")
    print("2. start_authorization()로 인증 URL 생성")
    print("3. 브라우저에서 인증 후 코드 복사")
    print("4. complete_authorization()로 토큰 발급")
    print("5. test_api()로 API 테스트")