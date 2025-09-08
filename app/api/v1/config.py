from flask import Blueprint, jsonify
from config.settings import settings

config_bp = Blueprint('config', __name__)

@config_bp.route('/config', methods=['GET'])
def get_config():
    """현재 설정 조회"""
    try:
        return jsonify({
            'cafe24': {
                'client_id': settings.cafe24_client_id,
                'mall_id': settings.cafe24_id,
                'redirect_uri': settings.cafe24_redirect_uri,
                'configured': bool(settings.cafe24_client_id and settings.cafe24_client_secret)
            },
            'monitoring': {
                'check_interval': settings.check_interval,
                'max_reviews_per_check': settings.max_reviews_per_check,
                'notification_enabled': settings.notification_enabled
            },
            'app': {
                'debug': settings.debug,
                'port': settings.port,
                'host': settings.host
            },
            'webhook': {
                'enabled': True,
                'event_key_configured': bool(settings.WEBHOOK_EVENT_KEY)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500