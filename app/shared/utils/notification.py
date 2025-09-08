"""
알림 관리 유틸리티
"""

import json
import os
import requests
from datetime import datetime
from typing import List, Dict, Any
from collections import deque


class NotificationManager:
    """알림 관리 클래스"""
    
    def __init__(self, max_notifications: int = 100):
        self.max_notifications = max_notifications
        self.pending_notifications = deque(maxlen=max_notifications)
        self.notification_history_file = "notification_history.json"
        
        # 카카오톡 설정
        from config.settings import settings
        self.kakao_api_key = settings.kakao_api_key
        self.kakao_access_token = settings.kakao_access_token  # 환경변수에서 초기화
        self.kakao_refresh_token = None  # 리프레시 토큰
        
        # 채널톡 설정
        self.channel_talk_access_token = settings.channel_talk_access_key
        self.channel_talk_secret = settings.channel_talk_secret_key
        self.channel_talk_group_id = settings.channel_talk_group_id
        
    def add_notification(self, title: str, message: str, notification_type: str = "info", 
                        data: Dict[str, Any] = None) -> Dict[str, Any]:
        """알림 추가"""
        notification = {
            'id': self._generate_notification_id(),
            'title': title,
            'message': message,
            'type': notification_type,  # info, warning, error, success
            'timestamp': datetime.now().isoformat(),
            'data': data or {},
            'read': False
        }
        
        self.pending_notifications.append(notification)
        # 클라우드 환경에서는 파일 저장 비활성화
        # self._save_to_history(notification)
        
        return notification
    
    def add_review_notification(self, new_reviews: List[Dict], negative_reviews: List[Dict]) -> Dict[str, Any]:
        """리뷰 관련 알림 추가"""
        if negative_reviews:
            # 부정 리뷰가 있으면 경고 알림
            title = f"⚠️ 부정 리뷰 {len(negative_reviews)}개 발견!"
            message = f"신규 리뷰 총 {len(new_reviews)}개 중 부정 리뷰 발견"
            notification_type = "warning"
            
            # 부정 리뷰 샘플 추가
            sample_review = negative_reviews[0]['content'][:100] if negative_reviews[0].get('content') else "내용 없음"
            message += f"\n예시: {sample_review}..."
            
        else:
            # 일반 신규 리뷰 알림
            title = f"📝 신규 리뷰 {len(new_reviews)}개 발견"
            message = f"새로운 리뷰가 등록되었습니다."
            notification_type = "info"
            
            if new_reviews:
                sample_review = new_reviews[0]['content'][:100] if new_reviews[0].get('content') else "내용 없음"
                message += f"\n최신 리뷰: {sample_review}..."
        
        data = {
            'new_count': len(new_reviews),
            'negative_count': len(negative_reviews),
            'reviews': new_reviews[:5],  # 최대 5개만 저장
            'negative_reviews': negative_reviews[:3]  # 부정 리뷰 최대 3개
        }
        
        return self.add_notification(title, message, notification_type, data)
    
    def add_system_notification(self, message: str, level: str = "info") -> Dict[str, Any]:
        """시스템 관련 알림 추가"""
        icons = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌',
            'success': '✅'
        }
        
        title = f"{icons.get(level, 'ℹ️')} 시스템 알림"
        
        return self.add_notification(title, message, level)
    
    def add_monitoring_notification(self, status: str, message: str, data: Dict = None) -> Dict[str, Any]:
        """모니터링 관련 알림 추가"""
        status_config = {
            'started': {
                'title': '🟢 모니터링 시작',
                'type': 'success'
            },
            'stopped': {
                'title': '🔴 모니터링 중지',
                'type': 'warning'
            },
            'error': {
                'title': '❌ 모니터링 오류',
                'type': 'error'
            },
            'paused': {
                'title': '⏸️ 모니터링 일시 중지',
                'type': 'warning'
            }
        }
        
        config = status_config.get(status, {
            'title': 'ℹ️ 모니터링 상태 변경',
            'type': 'info'
        })
        
        return self.add_notification(config['title'], message, config['type'], data)
    
    def get_pending_notifications(self, mark_as_read: bool = True) -> List[Dict[str, Any]]:
        """대기 중인 알림 목록 반환"""
        notifications = list(self.pending_notifications)
        
        if mark_as_read:
            # 읽음 처리
            for notification in self.pending_notifications:
                notification['read'] = True
            
            # 읽은 알림 제거
            self.pending_notifications.clear()
        
        return notifications
    
    def get_unread_count(self) -> int:
        """읽지 않은 알림 개수"""
        return len([n for n in self.pending_notifications if not n.get('read', False)])
    
    def clear_notifications(self):
        """모든 대기 중인 알림 제거"""
        self.pending_notifications.clear()
    
    def get_recent_notifications(self, limit: int = 10) -> List[Dict[str, Any]]:
        """최근 알림 기록 조회"""
        try:
            if os.path.exists(self.notification_history_file):
                with open(self.notification_history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    
                # 최신순으로 정렬
                history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                
                return history[:limit]
        except Exception as e:
            print(f"알림 기록 조회 실패: {e}")
        
        return []
    
    def _generate_notification_id(self) -> str:
        """알림 ID 생성"""
        from uuid import uuid4
        return str(uuid4())[:8]
    
    def _save_to_history(self, notification: Dict[str, Any]):
        """알림을 기록 파일에 저장"""
        try:
            history = []
            
            # 기존 기록 로드
            if os.path.exists(self.notification_history_file):
                with open(self.notification_history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            # 새 알림 추가
            history.append(notification)
            
            # 최대 개수 제한
            if len(history) > self.max_notifications:
                history = history[-self.max_notifications:]
            
            # 저장
            with open(self.notification_history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"알림 기록 저장 실패: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """알림 통계 정보"""
        recent_notifications = self.get_recent_notifications(100)
        
        # 타입별 통계
        type_counts = {}
        for notification in recent_notifications:
            notification_type = notification.get('type', 'info')
            type_counts[notification_type] = type_counts.get(notification_type, 0) + 1
        
        # 최근 24시간 통계
        from datetime import datetime, timedelta
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        
        recent_24h = []
        for notification in recent_notifications:
            try:
                timestamp = datetime.fromisoformat(notification.get('timestamp', ''))
                if timestamp >= last_24h:
                    recent_24h.append(notification)
            except:
                continue
        
        return {
            'total_notifications': len(recent_notifications),
            'unread_count': self.get_unread_count(),
            'pending_count': len(self.pending_notifications),
            'last_24h_count': len(recent_24h),
            'type_counts': type_counts,
            'last_notification': recent_notifications[0] if recent_notifications else None
        }
    
    def export_notifications(self, filepath: str = None) -> str:
        """알림 기록 내보내기"""
        if filepath is None:
            filepath = f"notifications_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            notifications = self.get_recent_notifications(1000)  # 최근 1000개
            
            export_data = {
                'export_date': datetime.now().isoformat(),
                'total_count': len(notifications),
                'notifications': notifications
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            return filepath
            
        except Exception as e:
            print(f"알림 내보내기 실패: {e}")
            return None
    
    def print_pending_notifications(self):
        """대기 중인 알림 콘솔 출력"""
        notifications = list(self.pending_notifications)
        
        if not notifications:
            print("대기 중인 알림이 없습니다.")
            return
        
        print(f"\n=== 대기 중인 알림 ({len(notifications)}개) ===")
        
        for i, notification in enumerate(notifications, 1):
            print(f"{i}. [{notification.get('type', 'info').upper()}] {notification.get('title', '')}")
            print(f"   {notification.get('message', '')}")
            print(f"   시간: {notification.get('timestamp', '')}")
            
            if notification.get('data'):
                data = notification['data']
                if 'new_count' in data:
                    print(f"   신규 리뷰: {data.get('new_count', 0)}개")
                if 'negative_count' in data:
                    print(f"   부정 리뷰: {data.get('negative_count', 0)}개")
            
            print()


    def send_kakao_message(self, message: str, access_token: str = None) -> bool:
        """카카오톡 나에게 보내기"""
        if not access_token and not self.kakao_access_token:
            print("⚠️ 카카오톡 액세스 토큰이 없습니다.")
            return False
            
        token = access_token or self.kakao_access_token
        
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # 메시지 템플릿
        template = {
            "object_type": "text",
            "text": message,
            "link": {
                "web_url": "https://cilantro-comment-detector-738575764165.asia-northeast3.run.app",
                "mobile_web_url": "https://cilantro-comment-detector-738575764165.asia-northeast3.run.app"
            }
        }
        
        data = {
            "template_object": json.dumps(template)
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            
            print("✅ 카카오톡 메시지 전송 성공")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 카카오톡 메시지 전송 실패: {e}")
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('msg', str(e))
                    error_code = error_data.get('code', 'Unknown')
                    print(f"카카오 API 에러 [{error_code}]: {error_msg}")
                except:
                    print(f"응답: {e.response.text}")
            return False
    
    def get_kakao_auth_url(self) -> str:
        """카카오톡 인증 URL 생성"""
        if not self.kakao_api_key:
            return None
            
        from urllib.parse import urlencode
        
        params = {
            "client_id": self.kakao_api_key,
            "redirect_uri": "https://cilantro-comment-detector-738575764165.asia-northeast3.run.app/auth/kakao/callback",
            "response_type": "code",
            "scope": "talk_message"
        }
        
        # 강제 재인증을 위한 prompt 파라미터 추가
        params["prompt"] = "login"
        
        return f"https://kauth.kakao.com/oauth/authorize?{urlencode(params)}"
    
    def get_kakao_access_token(self, authorization_code: str) -> str:
        """카카오톡 액세스 토큰 발급"""
        if not self.kakao_api_key:
            return None
            
        url = "https://kauth.kakao.com/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "client_id": self.kakao_api_key,
            "redirect_uri": "https://cilantro-comment-detector-738575764165.asia-northeast3.run.app/auth/kakao/callback",
            "code": authorization_code
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            print(f"🔍 카카오톡 토큰 응답: {token_data}")
            
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            
            if access_token:
                self.kakao_access_token = access_token
                self.kakao_refresh_token = refresh_token  # 리프레시 토큰도 저장
                print(f"✅ 카카오톡 토큰 발급 성공:")
                print(f"   액세스 토큰: {access_token[:10]}...")
                print(f"   리프레시 토큰: {'있음' if refresh_token else '없음'}")
                print(f"   만료시간: {expires_in}초")
                
                # 토큰을 환경변수 파일에도 저장 (선택사항)
                self._save_access_token_to_env(access_token)
                
            return access_token
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 카카오톡 토큰 발급 실패: {e}")
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error_description', error_data.get('error', str(e)))
                    print(f"카카오 OAuth 에러: {error_msg}")
                except:
                    print(f"응답: {e.response.text}")
            return None
    
    def _save_access_token_to_env(self, access_token: str):
        """액세스 토큰을 .env 파일에 저장"""
        try:
            import os
            env_path = ".env"
            
            if os.path.exists(env_path):
                # .env 파일 읽기
                with open(env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # KAKAO_ACCESS_TOKEN 라인 찾아서 업데이트
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith('KAKAO_ACCESS_TOKEN='):
                        lines[i] = f'KAKAO_ACCESS_TOKEN={access_token}\n'
                        updated = True
                        break
                
                # 없으면 추가
                if not updated:
                    lines.append(f'KAKAO_ACCESS_TOKEN={access_token}\n')
                
                # .env 파일 쓰기
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                print("✅ 카카오톡 액세스 토큰을 .env 파일에 저장했습니다.")
                
        except Exception as e:
            print(f"⚠️ .env 파일 저장 실패: {e}")
    
    def send_review_alert_to_kakao(self, new_reviews: List[Dict], negative_reviews: List[Dict]) -> bool:
        """부정 리뷰 알림을 카카오톡으로 전송"""
        if not self.kakao_access_token:
            print("⚠️ 카카오톡 인증이 필요합니다.")
            return False
            
        if not negative_reviews and not new_reviews:
            return True
            
        # 메시지 구성
        if negative_reviews:
            message = f"🚨 부정 리뷰 {len(negative_reviews)}개 발견!\n"
            message += f"신규 리뷰 총 {len(new_reviews)}개 중 부정 리뷰가 발견되었습니다.\n\n"
            
            # 부정 리뷰 샘플 추가 (최대 2개)
            for i, review in enumerate(negative_reviews[:2]):
                content = review.get('content', '내용 없음')[:50]
                message += f"• {content}...\n"
                
            if len(negative_reviews) > 2:
                message += f"• 외 {len(negative_reviews) - 2}개 더\n"
                
        else:
            message = f"📝 신규 리뷰 {len(new_reviews)}개 발견\n"
            message += f"새로운 리뷰가 등록되었습니다.\n\n"
            
            if new_reviews:
                content = new_reviews[0].get('content', '내용 없음')[:50]
                message += f"최신: {content}...\n"
        
        message += f"\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message += f"\n대시보드에서 자세히 보기 ↓"
        
        return self.send_kakao_message(message)
    
    def send_channel_talk_message(self, message: str, group_id: str = None) -> bool:
        """채널톡 팀 채팅 그룹에 메시지 전송"""
        if not self.channel_talk_access_token or not self.channel_talk_secret:
            print("⚠️ 채널톡 인증 정보가 없습니다.")
            return False
        
        # 그룹 ID 사용 (환경변수 또는 파라미터)
        target_group_id = group_id or self.channel_talk_group_id
        if not target_group_id:
            print("⚠️ 채널톡 그룹 ID가 없습니다.")
            return False
        
        # 채널톡 팀 채팅 메시지 전송 API
        url = f"https://api.channel.io/open/v5/groups/{target_group_id}/messages"
        
        headers = {
            "x-access-key": self.channel_talk_access_token,
            "x-access-secret": self.channel_talk_secret,
            "Content-Type": "application/json"
        }
        
        # 메시지 데이터 구성
        data = {
            "blocks": [
                {
                    "type": "text",
                    "value": message
                }
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            print(f"✅ 채널톡 메시지 전송 성공 (그룹 ID: {target_group_id})")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 채널톡 메시지 전송 실패: {e}")
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('message', str(e))
                    error_code = error_data.get('code', 'Unknown')
                    print(f"채널톡 API 에러 [{error_code}]: {error_msg}")
                except:
                    print(f"응답: {e.response.text}")
            return False
    
    def send_review_alert_to_channel_talk(self, new_reviews: List[Dict], negative_reviews: List[Dict], channel_id: str = None) -> bool:
        """부정 리뷰 알림을 채널톡으로 전송"""
        if not self.channel_talk_access_token:
            print("⚠️ 채널톡 토큰이 없습니다. 환경변수에서 다시 로드 시도...")
            from config.settings import settings
            self.channel_talk_access_token = settings.channel_talk_access_key
            self.channel_talk_secret = settings.channel_talk_secret_key
            self.channel_talk_group_id = settings.channel_talk_group_id
            
        if not self.channel_talk_access_token:
            print("❌ 채널톡 인증이 필요합니다. CHANNEL_TALK_ACCESS_TOKEN 환경변수를 확인하세요.")
            return False
            
        if not negative_reviews and not new_reviews:
            return True
            
        # 메시지 구성
        if negative_reviews:
            # 부정 + 중립 리뷰 분류
            actual_negative = [r for r in negative_reviews if r.get('is_negative', False)]
            neutral_reviews = [r for r in negative_reviews if not r.get('is_negative', False)]
            
            message = f"🚨 주의 필요한 리뷰 발견!\n"
            if actual_negative:
                message += f"부정 리뷰: {len(actual_negative)}개"
            if neutral_reviews:
                message += f" | 중립 리뷰: {len(neutral_reviews)}개"
            message += f"\n{'=' * 40}\n\n"
            
            # 각 리뷰의 상세 정보
            for i, review in enumerate(negative_reviews):
                review_type = "🔴 부정" if review.get('is_negative', False) else "🟡 중립"
                message += f"📌 {review_type} 리뷰 #{i+1}\n"
                message += f"상품명: {review.get('product_name', '알 수 없음')}\n"
                message += f"제목: {review.get('title', '제목 없음')}\n"
                message += f"내용: {review.get('content', '내용 없음')}\n"
                message += f"별점: {'⭐' * int(review.get('rating', 0))} ({review.get('rating', 0)}/5)\n"
                message += f"작성자: {review.get('writer', '익명')}\n"
                message += f"등록시간: {review.get('created_date', '시간 정보 없음')}\n"
                message += f"신뢰도: {review.get('confidence', 0):.2f}\n"
                message += "-" * 30 + "\n\n"
                
        else:
            # 일반 신규 리뷰인 경우 - 간단한 정보
            message = f"📝 신규 리뷰 {len(new_reviews)}개 발견\n"
            message += f"새로운 리뷰가 등록되었습니다.\n\n"
            
            if new_reviews:
                latest_review = new_reviews[0]
                message += f"최신 리뷰:\n"
                message += f"상품명: {latest_review.get('product_name', '알 수 없음')}\n"
                message += f"제목: {latest_review.get('title', '제목 없음')}\n"
                message += f"내용: {latest_review.get('content', '내용 없음')[:100]}...\n"
                message += f"별점: {'⭐' * int(latest_review.get('rating', 0))} ({latest_review.get('rating', 0)}/5)\n"
        
        message += f"\n🕐 알림 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message += f"\n🔗 대시보드: https://cilantro-comment-detector-738575764165.asia-northeast3.run.app"
        
        return self.send_channel_talk_message(message, channel_id)
    
    def send_notification_to_all(self, new_reviews: List[Dict], negative_reviews: List[Dict], 
                                notification_method: str = "both") -> Dict[str, bool]:
        """모든 알림 채널로 알림 전송
        
        Args:
            new_reviews: 신규 리뷰 목록
            negative_reviews: 부정 리뷰 목록
            notification_method: "kakao", "channel_talk", "both"
            
        Returns:
            각 채널별 전송 결과
        """
        results = {}
        
        if notification_method in ["kakao", "both"]:
            if self.kakao_access_token:
                results["kakao"] = self.send_review_alert_to_kakao(new_reviews, negative_reviews)
            else:
                results["kakao"] = False
                print("⚠️ 카카오톡 토큰이 없어 전송하지 않습니다.")
        
        if notification_method in ["channel_talk", "both"]:
            # 채널톡 토큰 재확인 및 재시도
            if not self.channel_talk_access_token:
                print("⚠️ 채널톡 토큰이 없습니다. 환경변수에서 다시 로드 시도...")
                from config.settings import settings
                self.channel_talk_access_token = settings.channel_talk_access_key
                self.channel_talk_secret = settings.channel_talk_secret_key
                self.channel_talk_group_id = settings.channel_talk_group_id
            
            if self.channel_talk_access_token:
                results["channel_talk"] = self.send_review_alert_to_channel_talk(new_reviews, negative_reviews)
            else:
                results["channel_talk"] = False
                print("❌ 채널톡 토큰을 찾을 수 없습니다. CHANNEL_TALK_ACCESS_TOKEN 환경변수를 확인하세요.")
        
        return results

    def send_simple_channel_talk_message(self, message: str, group_id: str = None) -> bool:
        """간단한 채널톡 메시지 전송 (웹훅용)"""
        if not self.channel_talk_access_token:
            # 토큰 재로드 시도
            from config.settings import settings
            self.channel_talk_access_token = settings.channel_talk_access_key
            self.channel_talk_secret = settings.channel_talk_secret_key
            self.channel_talk_group_id = settings.channel_talk_group_id
            
        if not self.channel_talk_access_token:
            print("❌ 채널톡 토큰을 찾을 수 없습니다.")
            return False
            
        return self.send_message_to_channel_talk(message, group_id)


# 전역 알림 관리자 인스턴스
notification_manager = NotificationManager()