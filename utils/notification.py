"""
알림 관리 유틸리티
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any
from collections import deque


class NotificationManager:
    """알림 관리 클래스"""
    
    def __init__(self, max_notifications: int = 100):
        self.max_notifications = max_notifications
        self.pending_notifications = deque(maxlen=max_notifications)
        self.notification_history_file = "notification_history.json"
        
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
        self._save_to_history(notification)
        
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


# 전역 알림 관리자 인스턴스
notification_manager = NotificationManager()