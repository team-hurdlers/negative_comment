"""
카페24 리뷰 API 클래스
"""

import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import time


class Cafe24ReviewAPI:
    """카페24 API를 통한 리뷰 수집 클래스"""
    
    def __init__(self, oauth_client):
        """
        Args:
            oauth_client: Cafe24OAuth 인스턴스
        """
        self.oauth = oauth_client
        self.base_url = oauth_client.base_url
        self.rate_limit_delay = 0.5  # API 호출 간격 (초)
        
    def _get_headers(self) -> dict:
        """API 호출용 헤더 생성"""
        token = self.oauth.get_valid_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-Cafe24-Api-Version': '2025-06-01'
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """API 요청 공통 함수"""
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()
        
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"API 요청 실패 [{method} {endpoint}]: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"응답 내용: {e.response.text}")
            raise
    
    def get_boards(self, board_type: str = None) -> List[Dict]:
        """
        게시판 목록 조회
        
        Args:
            board_type: 게시판 타입 필터
            
        Returns:
            게시판 목록
        """
        params = {}
        if board_type:
            params['board_type'] = board_type
            
        result = self._make_request('GET', 'admin/boards', params=params)
        return result.get('boards', [])
    
    def get_review_boards(self) -> List[Dict]:
        """리뷰 게시판만 필터링하여 조회"""
        boards = self.get_boards()
        review_boards = []
        
        for board in boards:
            board_name = board.get('board_name', '').lower()
            if any(keyword in board_name for keyword in ['review', '리뷰', '후기', '평가']):
                review_boards.append(board)
                
        return review_boards
    
    def get_board_articles(self, board_no: int, limit: int = 100, offset: int = 0, 
                          start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        특정 게시판의 게시글 목록 조회
        
        Args:
            board_no: 게시판 번호
            limit: 조회할 게시글 수
            offset: 시작 위치
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            
        Returns:
            게시글 목록
        """
        params = {
            'limit': limit,
            'offset': offset,
            'fields': 'article_no,title,content,writer,created_date,product_no,rating'
        }
        
        if start_date:
            params['created_start_date'] = start_date
        if end_date:
            params['created_end_date'] = end_date
            
        result = self._make_request('GET', f'admin/boards/{board_no}/articles', params=params)
        return result.get('articles', [])
    
    def get_article_detail(self, board_no: int, article_no: int) -> Dict:
        """
        게시글 상세 조회
        
        Args:
            board_no: 게시판 번호
            article_no: 게시글 번호
            
        Returns:
            게시글 상세 정보
        """
        params = {
            'fields': 'article_no,title,content,writer,created_date,updated_date,view_count,product_no,rating'
        }
        result = self._make_request('GET', f'admin/boards/{board_no}/articles/{article_no}', params=params)
        return result.get('article', {})
    
    def get_product_reviews(self, product_no: int = None, limit: int = 100) -> List[Dict]:
        """
        특정 상품의 리뷰 수집
        
        Args:
            product_no: 상품 번호 (None이면 전체 리뷰)
            limit: 조회할 리뷰 수
            
        Returns:
            리뷰 목록
        """
        reviews = []
        
        try:
            # 리뷰 게시판 찾기
            review_boards = self.get_review_boards()
            
            if not review_boards:
                print("리뷰 게시판을 찾을 수 없습니다.")
                return reviews
            
            # 각 리뷰 게시판에서 리뷰 수집
            for board in review_boards:
                board_no = board['board_no']
                print(f"게시판 '{board['board_name']}' (번호: {board_no})에서 리뷰 수집 중...")
                
                # 게시글 목록 조회
                articles = self.get_board_articles(board_no, limit=limit)
                
                for article in articles:
                    # 상품 번호 필터링
                    if product_no and article.get('product_no') != product_no:
                        continue
                    
                    # 각 게시글의 전체 내용을 가져오기 위해 상세 조회
                    detailed_article = self.get_article_detail(board_no, article['article_no'])
                    
                    # 리뷰 데이터 구성
                    review = {
                        'board_no': board_no,
                        'board_name': board['board_name'],
                        'article_no': article['article_no'],
                        'product_no': detailed_article.get('product_no') or article.get('product_no'),
                        'title': detailed_article.get('title') or article.get('title', ''),
                        'content': detailed_article.get('content') or article.get('content', ''),
                        'writer': detailed_article.get('writer') or article.get('writer', ''),
                        'rating': detailed_article.get('rating') or article.get('rating', 0),
                        'created_date': detailed_article.get('created_date') or article.get('created_date', ''),
                        'view_count': detailed_article.get('view_count') or article.get('view_count', 0)
                    }
                    
                    reviews.append(review)
                
                # 수집량이 충분하면 중단
                if len(reviews) >= limit:
                    break
            
            print(f"총 {len(reviews)}개의 리뷰를 수집했습니다.")
            
        except Exception as e:
            print(f"리뷰 수집 중 오류 발생: {e}")
        
        return reviews[:limit]
    
    def get_latest_reviews(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """
        최근 N일간의 리뷰 조회
        
        Args:
            days: 조회할 일수
            limit: 최대 조회 수
            
        Returns:
            최신 리뷰 목록
        """
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        reviews = []
        review_boards = self.get_review_boards()
        
        for board in review_boards:
            board_no = board['board_no']
            articles = self.get_board_articles(
                board_no, 
                limit=limit,
                start_date=start_date_str,
                end_date=end_date_str
            )
            
            for article in articles:
                # HTML 태그 정리
                content = article.get('content', '').replace('<br>:', '\n').replace('<br>', '\n')
                
                review = {
                    'board_no': board_no,
                    'board_name': board['board_name'],
                    'article_no': article['article_no'],
                    'product_no': article.get('product_no'),
                    'title': article.get('title', ''),
                    'content': content,
                    'writer': article.get('writer', ''),
                    'rating': article.get('rating', 0),
                    'created_date': article.get('created_date', ''),
                    'view_count': article.get('view_count', 0)
                }
                
                reviews.append(review)
        
        # 날짜순 정렬 (최신순)
        reviews.sort(key=lambda x: x['created_date'], reverse=True)
        
        return reviews[:limit]
    
    def search_reviews(self, keyword: str, limit: int = 50) -> List[Dict]:
        """
        키워드로 리뷰 검색
        
        Args:
            keyword: 검색 키워드
            limit: 최대 조회 수
            
        Returns:
            검색된 리뷰 목록
        """
        reviews = []
        review_boards = self.get_review_boards()
        
        for board in review_boards:
            board_no = board['board_no']
            
            # 게시판별 검색 파라미터
            params = {
                'limit': limit,
                'search_type': 'content',  # 내용으로 검색
                'search_keyword': keyword,
                'fields': 'article_no,title,content,writer,created_date,updated_date,view_count,product_no,rating'
            }
            
            try:
                result = self._make_request('GET', f'admin/boards/{board_no}/articles', params=params)
                articles = result.get('articles', [])
                
                for article in articles:
                    # 각 게시글의 전체 내용을 가져오기 위해 상세 조회
                    detailed_article = self.get_article_detail(board_no, article['article_no'])
                    
                    review = {
                        'board_no': board_no,
                        'board_name': board['board_name'],
                        'article_no': article['article_no'],
                        'product_no': detailed_article.get('product_no') or article.get('product_no'),
                        'title': detailed_article.get('title') or article.get('title', ''),
                        'content': detailed_article.get('content') or article.get('content', ''),
                        'writer': detailed_article.get('writer') or article.get('writer', ''),
                        'rating': detailed_article.get('rating') or article.get('rating', 0),
                        'created_date': detailed_article.get('created_date') or article.get('created_date', ''),
                        'view_count': detailed_article.get('view_count') or article.get('view_count', 0)
                    }
                    
                    reviews.append(review)
                    
            except Exception as e:
                print(f"게시판 {board_no} 검색 중 오류: {e}")
                continue
        
        return reviews[:limit]
    
    def get_products(self, limit: int = 100) -> List[Dict]:
        """
        상품 목록 조회
        
        Args:
            limit: 조회할 상품 수
            
        Returns:
            상품 목록
        """
        params = {
            'limit': limit,
            'fields': 'product_no,product_name,product_code,price,display'
        }
        
        result = self._make_request('GET', 'admin/products', params=params)
        return result.get('products', [])
    
    def get_product_info(self, product_no: int) -> Dict:
        """
        특정 상품 정보 조회
        
        Args:
            product_no: 상품 번호
            
        Returns:
            상품 정보
        """
        try:
            result = self._make_request('GET', f'admin/products/{product_no}', 
                                        params={'fields': 'product_no,product_name'})
            return result.get('product', {})
        except Exception as e:
            print(f"상품 {product_no} 정보 조회 오류: {e}")
            return {}