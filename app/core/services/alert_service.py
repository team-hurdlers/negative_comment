from datetime import datetime

class AlertService:
    def __init__(self, notification_manager=None):
        self.notification_manager = notification_manager
    
    def send_negative_review_alert(self, content, analysis_result):
        """부정 리뷰 감지 시 즉시 알림 발송"""
        try:
            alert_data = {
                'type': 'negative_review_detected',
                'content': content['text'][:200],
                'author': content.get('author', 'Unknown'),
                'score': analysis_result.get('score', 0),
                'confidence': analysis_result.get('confidence', 0),
                'source': content.get('source', 'webhook'),
                'detected_at': datetime.now().isoformat()
            }
            
            print(f"📡 알림 데이터 생성: {alert_data}")
            
            # 알림 매니저에 긴급 알림 추가
            notification_result = self.notification_manager.add_monitoring_notification(
                'urgent_negative_review',
                f"🚨 긴급! 부정 리뷰 감지: {content['text'][:50]}...",
                alert_data
            )
            
            print(f"📢 알림 매니저 결과: {notification_result}")
            print(f"✅ 부정 리뷰 긴급 알림 발송 완료: {content['text'][:50]}...")
            
        except Exception as e:
            print(f"❌ 부정 리뷰 알림 발송 오류: {e}")
            import traceback
            traceback.print_exc()

    def trigger_review_collection(self, review_api, find_new_reviews_func, analyze_reviews_batch_func, settings):
        """웹훅 트리거 시 신규 리뷰만 수집하고 분석"""
        try:
            if not review_api:
                print("❌ Review API가 없습니다.")
                return False
                
            print("🔍 웹훅 트리거로 인한 신규 리뷰 수집 시작...")
            
            # 신규 리뷰만 찾기
            new_reviews = find_new_reviews_func()
            
            if new_reviews:
                print(f"📝 신규 리뷰 {len(new_reviews)}개에 대해 감정 분석 시작...")
                
                # 신규 리뷰들만 감정 분석 수행
                analyzed_reviews = analyze_reviews_batch_func(new_reviews)
                negative_reviews = [r for r in analyzed_reviews if r.get('is_negative', False)]
                # 긍정이지만 신뢰도가 낮은 경우 (실제로는 부정일 가능성)
                low_confidence_positive = [r for r in analyzed_reviews if not r.get('is_negative', False) and r.get('confidence', 0) < 60.0]
                
                if negative_reviews or low_confidence_positive:
                    print(f"🚨 신규 부정 리뷰 {len(negative_reviews)}개, 낮은 신뢰도 긍정 리뷰 {len(low_confidence_positive)}개 발견!")
                    
                    # 부정 + 낮은 신뢰도 긍정 리뷰 함께 전송
                    problematic_reviews = negative_reviews + low_confidence_positive
                    self.notification_manager.send_notification_to_all(new_reviews, problematic_reviews, settings.notification_method)
                    
                    # 웹훅 간단 알림 전송 (낮은 신뢰도 긍정 리뷰만)
                    for review in low_confidence_positive:
                        content_text = review.get('content', '') or review.get('title', '')
                        confidence = review.get('confidence', 0)
                        
                        webhook_message = f"⚠️ 검토 필요한 긍정 리뷰\n\n📝 내용: {content_text[:100]}{'...' if len(content_text) > 100 else ''}\n\n📊 신뢰도: {confidence}% (낮음)\n🔍 분석: 긍정적이지만 확신도 낮음\n💡 실제로는 부정적일 수 있으니 확인 필요\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        self.notification_manager.send_simple_channel_talk_message(webhook_message)
                else:
                    print(f"📝 웹훅 트리거: 긍정 리뷰만 있음 ({len(new_reviews)}개)")
                    
                print(f"✅ 신규 리뷰 분석 완료: 총 {len(new_reviews)}개, 부정 {len(negative_reviews)}개")
            else:
                print("📝 신규 리뷰가 없습니다.")
            
            return True
            
        except Exception as e:
            print(f"❌ 웹훅 트리거 리뷰 수집 오류: {e}")
            import traceback
            traceback.print_exc()
            return False