from flask import Blueprint, request, jsonify

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('/get_notifications')
def get_notifications():
    """대기 중인 알림 가져가기"""
    try:
        from flask import current_app
        
        notification_manager = current_app.config.get('notification_manager')
        review_service = current_app.config.get('review_service')
        
        notifications = []
        
        # NotificationManager에서 알림 가져오기
        if notification_manager:
            notifications = notification_manager.get_pending_notifications(mark_as_read=True)
        
        # 기존 pending_notifications도 포함 (하위 호환성)
        if review_service and review_service.pending_notifications:
            notifications.extend(review_service.pending_notifications)
            review_service.pending_notifications.clear()
        
        return jsonify({
            'notifications': notifications,
            'count': len(notifications)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notifications_bp.route('/recent')
def get_recent_notifications():
    """최근 알림 기록 조회"""
    try:
        from flask import current_app
        
        notification_manager = current_app.config.get('notification_manager')
        limit = request.args.get('limit', 10, type=int)
        
        recent = []
        if notification_manager:
            recent = notification_manager.get_recent_notifications(limit=limit)
        
        return jsonify({
            'notifications': recent,
            'count': len(recent)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notifications_bp.route('/statistics')
def get_notification_statistics():
    """알림 통계 정보"""
    try:
        from flask import current_app
        
        notification_manager = current_app.config.get('notification_manager')
        
        statistics = {}
        if notification_manager:
            statistics = notification_manager.get_statistics()
        
        return jsonify(statistics)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 하위 호환성을 위해 기존 경로도 지원
@notifications_bp.route('/get_notifications', methods=['GET'])
def get_notifications_compat():
    """하위 호환성을 위한 기존 경로"""
    return get_notifications()