from datetime import datetime
from app.infrastructure.auth.cafe24_oauth import Cafe24OAuth
from app.infrastructure.external.cafe24.cafe24_reviews import Cafe24ReviewAPI
from config.settings import settings

class WebhookService:
    def __init__(self, notification_manager=None):
        self.notification_manager = notification_manager
    
    def extract_content_from_webhook(self, webhook_data):
        """웹훅 데이터에서 리뷰/메시지 내용 추출"""
        try:
            event_type = webhook_data.get('eventType')
            data = webhook_data.get('data', {})
            
            # 이벤트 타입별 데이터 구조가 다름
            if event_type == 'review.created':
                return {
                    'text': data.get('content', ''),
                    'author': data.get('author', {}).get('name', 'Unknown'),
                    'rating': data.get('rating'),
                    'product': data.get('product', {}),
                    'created_at': data.get('createdAt'),
                    'source': 'channel_talk_review'
                }
            elif event_type == 'message.created':
                return {
                    'text': data.get('message', ''),
                    'author': data.get('user', {}).get('name', 'Unknown'),
                    'channel': data.get('channel', {}),
                    'created_at': data.get('createdAt'),
                    'source': 'channel_talk_message'
                }
            
            return None
            
        except Exception as e:
            print(f"웹훅 데이터 추출 오류: {e}")
            return None

    def extract_content_from_cafe24_webhook(self, webhook_data):
        """카페24 웹훅 데이터에서 게시판 글 내용 추출"""
        try:
            # 카페24 웹훅 데이터 구조에 맞게 추출
            resource = webhook_data.get('resource', {})
            
            return {
                'text': resource.get('content', '') or resource.get('title', ''),
                'author': resource.get('writer', {}).get('name') if isinstance(resource.get('writer'), dict) else resource.get('writer', 'Unknown'),
                'board_no': resource.get('board_no'),
                'article_no': resource.get('article_no'),
                'created_date': resource.get('created_date'),
                'source': 'cafe24_webhook'
            }
            
        except Exception as e:
            print(f"카페24 웹훅 데이터 추출 오류: {e}")
            return None

    def process_cafe24_webhook(self, webhook_data, oauth_client, review_api, trigger_review_collection_func):
        """카페24 웹훅 데이터 처리 (게시판 글 등록)"""
        try:
            event_no = webhook_data.get('event_no')
            event_type = f"event_{event_no}" if event_no else webhook_data.get('event_type')
            print(f"🔍 카페24 웹훅 처리 시작 - 이벤트 번호: {event_no}, 타입: {event_type}")
            
            # 게시판 글 등록 이벤트 처리 (event_no: 90033)
            if event_no == 90033 or event_type in ['board.created', 'board_created']:
                print(f"📝 카페24 게시판 글 등록 이벤트 수신 - 신규 리뷰 확인 시작!")
                
                # 웹훅을 트리거로 사용해서 기존 리뷰 조회 로직 실행
                if not review_api:
                    print("⚠️ Review API가 초기화되지 않음. 자동 초기화 시도...")
                    
                    # OAuth 클라이언트부터 초기화 (저장된 토큰 포함)
                    if not oauth_client:
                        try:
                            oauth_client = Cafe24OAuth(
                                client_id=settings.cafe24_client_id,
                                client_secret=settings.cafe24_client_secret, 
                                mall_id=settings.cafe24_id,
                                redirect_uri=settings.cafe24_redirect_uri
                            )
                            print("✅ OAuth 클라이언트 초기화 완료")
                            
                            # 저장된 토큰이 있는지 확인
                            token_status = oauth_client.get_token_status()
                            if not token_status['has_token'] or not token_status['token_valid']:
                                print(f"⚠️ 유효한 OAuth 토큰이 없습니다: {token_status['message']}")
                                # 토큰이 없으면 채널톡으로 알림만 전송
                                webhook_message = f"🔔 카페24 웹훅 수신\n새로운 게시판 글이 등록되었습니다.\n\n이벤트: {event_type}\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n⚠️ OAuth 토큰이 만료되어 상세 분석을 수행할 수 없습니다.\n관리자가 OAuth 재인증을 해주세요."
                                if self.notification_manager:
                                    self.notification_manager.send_simple_channel_talk_message(webhook_message)
                                return True
                                
                        except Exception as e:
                            print(f"❌ OAuth 클라이언트 초기화 실패: {e}")
                            return False
                    
                    # Review API 초기화 시도
                    try:
                        review_api = Cafe24ReviewAPI(oauth_client)
                        print("✅ Review API 자동 초기화 완료")
                    except Exception as e:
                        print(f"❌ Review API 자동 초기화 실패: {e}")
                        return False
                
                print("🔍 웹훅 트리거로 인한 신규 리뷰 조회 시작...")
                if trigger_review_collection_func:
                    trigger_review_collection_func()
                return True
            else:
                print(f"⏭️ 처리 대상이 아닌 이벤트: {event_type}")
            
            return False
            
        except Exception as e:
            print(f"❌ 카페24 웹훅 처리 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def process_channel_talk_webhook(self, webhook_data, analyze_review_func, send_negative_review_alert_func, trigger_review_collection_func, review_api):
        """채널톡 웹훅 데이터 처리"""
        try:
            event_type = webhook_data.get('eventType')
            print(f"🔍 웹훅 처리 시작 - 이벤트 타입: {event_type}")
            
            # 리뷰 관련 이벤트만 처리
            if event_type in ['review.created', 'review.updated', 'message.created']:
                print(f"📝 채널톡 웹훅 이벤트 수신: {event_type}")
                
                # 웹훅 데이터에서 리뷰/메시지 내용 추출
                content = self.extract_content_from_webhook(webhook_data)
                print(f"📄 추출된 내용: {content}")
                
                if content:
                    # 감정 분석 수행 (평점 정보 포함)
                    data = webhook_data.get('data', {})
                    rating = data.get('rating', 0)
                    
                    if analyze_review_func:
                        analysis_result = analyze_review_func(content['text'], rating)
                        print(f"🤖 감정 분석 결과: {analysis_result} (평점: {rating}점)")
                        
                        if analysis_result.get('is_negative', False):
                            print("🚨 부정 리뷰 감지! 알림 발송 시작...")
                            # 부정 리뷰 감지 - 알림 발송
                            if send_negative_review_alert_func:
                                send_negative_review_alert_func(content, analysis_result)
                            
                            # 즉시 카페24 API로 최신 리뷰도 확인
                            if review_api and trigger_review_collection_func:
                                trigger_review_collection_func()
                        else:
                            print("😊 긍정적/중성적 리뷰로 분류됨 - 알림 없음")
                    
                    return True
                else:
                    print("❌ 내용 추출 실패")
            else:
                print(f"⏭️ 처리 대상이 아닌 이벤트: {event_type}")
            
            return False
            
        except Exception as e:
            print(f"❌ 채널톡 웹훅 처리 오류: {e}")
            return False