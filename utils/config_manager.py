"""
설정 관리 유틸리티
"""

import os
import json
from typing import Dict, Any, Optional, List
try:
    from dotenv import load_dotenv
    load_dotenv()  # .env 파일 로드
except ImportError:
    pass


class ConfigManager:
    """애플리케이션 설정 관리"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        
    def load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"설정 파일 로드 실패: {e}")
                return self.get_default_config()
        else:
            # 기본 설정 생성
            default_config = self.get_default_config()
            self.save_config(default_config)
            return default_config
    
    def get_default_config(self) -> Dict[str, Any]:
        """기본 설정값 반환"""
        return {
            "cafe24": {
                "client_id": "",
                "client_secret": "",
                "mall_id": "cila01",
                "redirect_uri": "http://localhost:5000/callback"
            },
            "analysis": {
                "confidence_threshold": 0.7,
                "model_name": "nlptown/bert-base-multilingual-uncased-sentiment",
                "fallback_model": "cardiffnlp/twitter-roberta-base-sentiment-latest"
            },
            "monitoring": {
                "check_interval": 3600,  # 1시간
                "max_reviews_per_check": 100,
                "notification_enabled": True
            },
            "app": {
                "debug": True,
                "port": 5000,
                "host": "0.0.0.0"
            }
        }
    
    def save_config(self, config: Dict[str, Any] = None):
        """설정 파일 저장"""
        if config is None:
            config = self.config
            
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"설정이 {self.config_file}에 저장되었습니다.")
        except Exception as e:
            print(f"설정 저장 실패: {e}")
    
    def get(self, key: str, default=None) -> Any:
        """설정값 조회 (점 표기법 지원)"""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any, save: bool = True):
        """설정값 변경 (점 표기법 지원)"""
        keys = key.split('.')
        config = self.config
        
        # 중첩된 딕셔너리 경로 생성
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 값 설정
        config[keys[-1]] = value
        
        if save:
            self.save_config()
    
    def get_cafe24_config(self) -> Dict[str, str]:
        """카페24 API 설정 반환"""
        return self.get('cafe24', {})
    
    def set_cafe24_config(self, client_id: str, client_secret: str, 
                         mall_id: str = None, redirect_uri: str = None):
        """카페24 API 설정 업데이트"""
        config = self.get_cafe24_config()
        
        config['client_id'] = client_id
        config['client_secret'] = client_secret
        
        if mall_id:
            config['mall_id'] = mall_id
        if redirect_uri:
            config['redirect_uri'] = redirect_uri
        
        self.set('cafe24', config)
    
    def is_cafe24_configured(self) -> bool:
        """카페24 API 설정 완료 여부 확인"""
        config = self.get_cafe24_config()
        return bool(config.get('client_id') and config.get('client_secret'))
    
    def get_analysis_config(self) -> Dict[str, Any]:
        """분석 설정 반환"""
        return self.get('analysis', {})
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """모니터링 설정 반환"""
        return self.get('monitoring', {})
    
    def get_app_config(self) -> Dict[str, Any]:
        """앱 설정 반환"""
        return self.get('app', {})
    
    def update_config_from_env(self):
        """환경변수에서 설정 업데이트"""
        env_mappings = {
            'CAFE24_CLIENT_ID': 'cafe24.client_id',
            'CAFE24_CLIENT_SECRET': 'cafe24.client_secret',
            'CAFE24_MALL_ID': 'cafe24.mall_id',
            'CAFE24_ID': 'cafe24.mall_id',  # CAFE24_ID도 mall_id로 매핑
            'CAFE24_REDIRECT_URI': 'cafe24.redirect_uri',
            'APP_DEBUG': 'app.debug',
            'APP_PORT': 'app.port',
            'ANALYSIS_THRESHOLD': 'analysis.confidence_threshold'
        }
        
        updated = False
        for env_var, config_key in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value:
                # 타입 변환
                if config_key in ['app.debug']:
                    env_value = env_value.lower() in ('true', '1', 'yes')
                elif config_key in ['app.port']:
                    env_value = int(env_value)
                elif config_key in ['analysis.confidence_threshold']:
                    env_value = float(env_value)
                
                self.set(config_key, env_value, save=False)
                updated = True
        
        if updated:
            self.save_config()
            print("환경변수에서 설정을 업데이트했습니다.")
    
    def validate_config(self) -> Dict[str, List[str]]:
        """설정 유효성 검사"""
        errors = {}
        
        # 카페24 설정 검사
        cafe24_config = self.get_cafe24_config()
        if not cafe24_config.get('client_id'):
            errors.setdefault('cafe24', []).append('client_id가 설정되지 않았습니다.')
        if not cafe24_config.get('client_secret'):
            errors.setdefault('cafe24', []).append('client_secret이 설정되지 않았습니다.')
        if not cafe24_config.get('mall_id'):
            errors.setdefault('cafe24', []).append('mall_id가 설정되지 않았습니다.')
        
        # 분석 설정 검사
        analysis_config = self.get_analysis_config()
        threshold = analysis_config.get('confidence_threshold', 0.7)
        if not 0 <= threshold <= 1:
            errors.setdefault('analysis', []).append('confidence_threshold는 0과 1 사이의 값이어야 합니다.')
        
        # 모니터링 설정 검사
        monitoring_config = self.get_monitoring_config()
        interval = monitoring_config.get('check_interval', 3600)
        if interval < 60:
            errors.setdefault('monitoring', []).append('check_interval은 최소 60초 이상이어야 합니다.')
        
        return errors
    
    def print_config_status(self):
        """설정 상태 출력"""
        print("=== 설정 상태 ===")
        
        # 카페24 설정
        cafe24_config = self.get_cafe24_config()
        print(f"카페24 Mall ID: {cafe24_config.get('mall_id', 'N/A')}")
        print(f"카페24 Client ID: {'설정됨' if cafe24_config.get('client_id') else '미설정'}")
        print(f"카페24 Client Secret: {'설정됨' if cafe24_config.get('client_secret') else '미설정'}")
        
        # 분석 설정
        analysis_config = self.get_analysis_config()
        print(f"신뢰도 임계값: {analysis_config.get('confidence_threshold', 0.7)}")
        print(f"분석 모델: {analysis_config.get('model_name', 'N/A')}")
        
        # 모니터링 설정
        monitoring_config = self.get_monitoring_config()
        print(f"모니터링 간격: {monitoring_config.get('check_interval', 3600)}초")
        print(f"알림 활성화: {monitoring_config.get('notification_enabled', True)}")
        
        # 유효성 검사
        errors = self.validate_config()
        if errors:
            print("\n⚠️  설정 오류:")
            for section, error_list in errors.items():
                print(f"  {section}:")
                for error in error_list:
                    print(f"    - {error}")
        else:
            print("\n✅ 모든 설정이 유효합니다.")


# 전역 설정 인스턴스
config = ConfigManager()