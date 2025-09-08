from app.infrastructure.external.cafe24.cafe24_reviews import Cafe24ReviewAPI

class Cafe24Service:
    def __init__(self):
        self.product_cache = {}
    
    def enrich_reviews_with_product_names(self, reviews, review_api):
        """리뷰에 상품명 정보를 추가"""
        if not review_api:
            return reviews
        
        enriched_reviews = []
        
        for review in reviews:
            enriched_review = review.copy()
            product_no = review.get('product_no')
            
            if product_no:
                # 캐시 확인
                if product_no not in self.product_cache:
                    try:
                        product_info = review_api.get_product_info(product_no)
                        self.product_cache[product_no] = product_info.get('product_name', f'상품{product_no}')
                    except Exception as e:
                        print(f"상품 {product_no} 정보 조회 실패: {e}")
                        self.product_cache[product_no] = f'상품{product_no}'
                
                enriched_review['product_name'] = self.product_cache[product_no]
            else:
                enriched_review['product_name'] = '알 수 없음'
            
            enriched_reviews.append(enriched_review)
        
        return enriched_reviews

    def init_cafe24_client(self, oauth_client):
        """카페24 API 클라이언트 초기화 (OAuth 클라이언트 사용)"""
        review_api = None
        
        # OAuth 클라이언트가 있고 토큰이 있는 경우 Review API 초기화
        if oauth_client:
            try:
                token_status = oauth_client.get_token_status()
                
                if token_status['has_token']:
                    # Review API 클라이언트 초기화 (자동 갱신 기능 포함)
                    review_api = Cafe24ReviewAPI(oauth_client)
                    
                    print(f"✅ 카페24 Review API 클라이언트 초기화 완료")
                    print(f"   - Mall ID: {oauth_client.mall_id}")
                    print(f"   - 토큰 상태: {token_status['message']}")
                    
                    # API 연결 테스트
                    try:
                        boards = review_api.get_review_boards()
                        if boards:
                            print(f"📝 카페24 API 연결 테스트 성공! 리뷰 게시판 {len(boards)}개 발견")
                        else:
                            print("📝 카페24 API 연결은 성공했지만 리뷰 게시판을 찾을 수 없습니다.")
                    except Exception as test_error:
                        print(f"⚠️ 카페24 API 연결 테스트 실패: {test_error}")
                        if "401" in str(test_error):
                            print("   토큰이 만료되었을 수 있습니다. 다음 요청 시 자동으로 갱신됩니다.")
                    
                else:
                    print(f"❌ 유효한 토큰이 없습니다: {token_status['message']}")
                    print("   OAuth 인증을 통해 토큰을 발급받아주세요.")
                    
            except Exception as e:
                print(f"❌ Review API 클라이언트 초기화 실패: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"❌ OAuth 클라이언트가 초기화되지 않았습니다.")
            print("   환경변수를 확인하고 OAuth 클라이언트를 먼저 초기화해주세요.")
        
        return review_api