"""
리뷰 감정 분석기 - GPT-4o-mini 우선, pkl/transformers 폴백
"""

import os
import pickle
import json
import warnings
from typing import List, Dict, Any
import re
from config.settings import settings

warnings.filterwarnings('ignore')


class ReviewAnalyzer:
    """리뷰 감정 분석 클래스 - GPT-4o-mini 우선, pkl/transformers 폴백"""
    
    def __init__(self):
        self.openai_client = None
        self.pkl_model = None
        self.load_models()
        
    def load_models(self):
        """감정 분석 모델 로드 - pkl만 (GPT는 필요시 로드)"""
        # pkl 모델만 먼저 로드
        self._load_pkl_model()
    
    def _load_openai_client(self):
        """OpenAI 클라이언트 초기화"""
        if settings.openai_api_key:
            try:
                import openai
                self.openai_client = openai.OpenAI(api_key=settings.openai_api_key)
                print("✅ OpenAI GPT-4o-mini 클라이언트 초기화 완료")
            except Exception as e:
                print(f"⚠️ OpenAI 클라이언트 초기화 실패: {e}")
    
    def _load_pkl_model(self):
        """pkl 감정 분석 모델 로드"""
        model_path = "final_svm_sentiment_model.pkl"
        
        if os.path.exists(model_path):
            try:
                print(f"경량 감정 분석 모델 로드 시작: {model_path}")
                with open(model_path, 'rb') as f:
                    self.pkl_model = pickle.load(f)
                print("✅ 경량 감정 분석 모델 로드 완료")
            except Exception as e:
                print(f"❌ 경량 모델 로드 실패: {e}")
                self.pkl_model = None
        else:
            print(f"⚠️ 모델 파일을 찾을 수 없음: {model_path}")
    
    
    def clean_text(self, text: str) -> str:
        """텍스트 전처리"""
        if not text:
            return ""
        
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', text)
        
        # 특수문자 정리 (기본적인 문장부호는 유지)
        text = re.sub(r'[^\w\s가-힣.,!?()]', ' ', text)
        
        # 연속된 공백 제거
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def analyze_single_review(self, review_text: str, rating: int = None) -> Dict[str, Any]:
        """단일 리뷰 감정 분석 - pkl 1차, 충돌 시 GPT 2차"""
        if not review_text or not review_text.strip():
            return {
                'is_negative': False,
                'confidence': 0,
                'label': '분석불가',
                'score': 0,
                'method': 'none',
                'error': '텍스트 없음'
            }
        
        # 1차 분석: pkl 모델 사용
        pkl_result = self._analyze_with_pkl(review_text)
        if not pkl_result:
            return {
                'is_negative': False,
                'confidence': 0,
                'label': '분석불가',
                'score': 0,
                'method': 'pkl_failed',
                'error': 'pkl 모델 분석 실패'
            }
        
        # 2차 분석: 판단과 평점이 모순되는 경우 GPT로 재검증
        conflict_detected = False
        conflict_type = ""
        
        # Case 1: 부정 판단 + 5점 평점
        if pkl_result.get('is_negative') and rating == 5:
            conflict_detected = True
            conflict_type = "negative_with_5stars"
            print(f"🔄 충돌 감지: 부정 판단 + 5점 평점 → GPT 2차 분석 시작")
        
        # Case 2: 긍정 판단 + 낮은 평점 (1-3점)
        elif pkl_result.get('is_positive') and rating in [1, 2, 3]:
            conflict_detected = True
            conflict_type = "positive_with_low_rating"
            print(f"🔄 충돌 감지: 긍정 판단 + {rating}점 평점 → GPT 2차 분석 시작")
        
        if conflict_detected:
            # GPT 클라이언트가 없으면 이때 로드
            if self.openai_client is None:
                print("🔄 GPT 클라이언트 초기화 중...")
                self._load_openai_client()
            
            gpt_result = self._analyze_with_gpt(review_text, is_second_stage=True, conflict_type=conflict_type, rating=rating)
            if gpt_result:
                # GPT 결과를 우선 채택하되, pkl 결과도 기록
                gpt_result['first_stage_result'] = pkl_result
                gpt_result['conflict_resolved'] = True
                gpt_result['conflict_type'] = conflict_type
                print(f"🎯 GPT 2차 분석 완료: {gpt_result.get('label')} (1차: {pkl_result.get('label')} → 2차: {gpt_result.get('label')})")
                return gpt_result
            else:
                print(f"⚠️ GPT 2차 분석 실패, 1차 결과 유지")
        
        return pkl_result
    
    def _analyze_with_gpt(self, review_text: str, is_second_stage: bool = False, conflict_type: str = None, rating: int = None) -> Dict[str, Any]:
        """GPT-4o-mini를 이용한 감정 분석"""
        if not self.openai_client:
            return None
        
        try:
            if is_second_stage:
                if conflict_type == "negative_with_5stars":
                    prompt = f"""
다음은 5점 만점에 5점을 받은 리뷰이지만, 1차 AI 모델에서는 부정적으로 분류되었습니다.
평점과 내용 사이의 모순을 해결하기 위해 정확한 재분석이 필요합니다.

리뷰 내용: "{review_text}"
평점: ⭐⭐⭐⭐⭐ (5/5점)

다음을 고려하여 분석해주세요:
1. 평점이 5점이라는 사실
2. 한국어의 미묘한 표현과 문맥
3. 반어법이나 아이러니 사용 여부
4. 전반적인 만족도와 추천 의도

다음 중 하나로 분류해주세요:
- positive: 긍정적인 리뷰 (만족, 좋음, 추천 등)
- negative: 부정적인 리뷰 (불만, 나쁨, 비추천 등)  
- neutral: 중립적인 리뷰 (단순 설명, 객관적 정보 등)

JSON 형태로만 답변해주세요:
{{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0~1.0,
    "reasoning": "분석 근거"
}}
"""
                elif conflict_type == "positive_with_low_rating":
                    stars = "⭐" * rating
                    prompt = f"""
다음은 {rating}점 만점에 {rating}점을 받은 리뷰이지만, 1차 AI 모델에서는 긍정적으로 분류되었습니다.
평점과 내용 사이의 모순을 해결하기 위해 정확한 재분석이 필요합니다.

리뷰 내용: "{review_text}"
평점: {stars} ({rating}/5점)

다음을 고려하여 분석해주세요:
1. 평점이 {rating}점(낮음)이라는 사실
2. 한국어의 미묘한 표현과 문맥
3. 비꼬기나 간접적 불만 표현 여부
4. 실제 만족도와 불만 사항
5. 낮은 평점의 이유가 내용에 반영되어 있는지

다음 중 하나로 분류해주세요:
- positive: 긍정적인 리뷰 (만족, 좋음, 추천 등)
- negative: 부정적인 리뷰 (불만, 나쁨, 비추천 등)  
- neutral: 중립적인 리뷰 (단순 설명, 객관적 정보 등)

JSON 형태로만 답변해주세요:
{{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0~1.0,
    "reasoning": "분석 근거"
}}
"""
            else:
                prompt = f"""
다음 리뷰의 감정을 분석해주세요. 한국어 리뷰입니다.

리뷰 내용: "{review_text}"

다음 중 하나로 분류해주세요:
- positive: 긍정적인 리뷰 (만족, 좋음, 추천 등)
- negative: 부정적인 리뷰 (불만, 나쁨, 비추천 등)  
- neutral: 중립적인 리뷰 (단순 설명, 객관적 정보 등)

JSON 형태로만 답변해주세요:
{{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0~1.0,
    "reasoning": "분석 근거"
}}
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 한국어 리뷰 감정 분석 전문가입니다. JSON 형태로만 답변하세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # JSON 파싱
            try:
                gpt_result = json.loads(result_text)
                is_negative = gpt_result.get('sentiment') == 'negative'
                confidence = float(gpt_result.get('confidence', 0.5))
                
                # 3가지 카테고리 분류
                sentiment = gpt_result.get('sentiment')
                is_negative = (sentiment == 'negative')
                is_positive = (sentiment == 'positive')
                is_neutral = (sentiment == 'neutral')
                
                # 라벨 결정
                if sentiment == 'negative':
                    label = '부정적'
                elif sentiment == 'positive':
                    label = '긍정적'
                else:
                    label = '중립적'
                
                return {
                    'is_negative': is_negative,
                    'is_positive': is_positive,
                    'is_neutral': is_neutral,
                    'confidence': confidence,
                    'label': label,
                    'score': round(confidence * 100, 2),
                    'method': 'gpt-4o-mini-2nd' if is_second_stage else 'gpt-4o-mini',
                    'reasoning': gpt_result.get('reasoning', ''),
                    'sentiment': sentiment,
                    'original_result': gpt_result
                }
            except json.JSONDecodeError:
                print(f"❌ GPT-4o-mini JSON 파싱 실패: {result_text}")
                return None
                
        except Exception as e:
            print(f"❌ GPT-4o-mini 분석 실패: {e}")
            return None
    
    def _analyze_with_pkl(self, review_text: str) -> Dict[str, Any]:
        """pkl 모델을 이용한 감정 분석"""
        if not self.pkl_model:
            return None
        
        try:
            # 텍스트 전처리
            clean_text = self.clean_text(review_text)
            if not clean_text:
                return None
            
            # pkl 모델로 예측
            prediction = self.pkl_model.predict([clean_text])[0]
            probabilities = self.pkl_model.predict_proba([clean_text])[0]
            confidence = probabilities[prediction]  # 예측된 클래스의 실제 확률
            
            # 예측 결과를 표준 형태로 변환
            sentiment_map = {0: 'negative', 1: 'neutral', 2: 'positive'}
            sentiment = sentiment_map.get(prediction, 'neutral')
            
            # 3가지 카테고리 분류
            is_negative = (sentiment == 'negative')
            is_positive = (sentiment == 'positive')
            is_neutral = (sentiment == 'neutral')
            
            # 신뢰도를 백분율로 변환 (0~100% 범위로 제한)
            confidence_percent = round(max(0.0, min(confidence * 100, 100.0)), 2)
            
            # 낮은 신뢰도 체크 (60% 이하)
            low_confidence = confidence < 0.6
            
            # 라벨 결정
            if low_confidence:
                if sentiment == 'negative':
                    label = "부정적 (확인 필요)"
                elif sentiment == 'positive':
                    label = "긍정적 (확인 필요)"
                else:
                    label = "중립적 (확인 필요)"
            else:
                if sentiment == 'negative':
                    label = '부정적'
                elif sentiment == 'positive':
                    label = '긍정적'
                else:
                    label = '중립적'
            
            return {
                'is_negative': is_negative,
                'is_positive': is_positive,
                'is_neutral': is_neutral,
                'sentiment': sentiment,
                'confidence': confidence_percent,
                'label': label,
                'score': confidence_percent,
                'method': 'pkl_model',
                'original_prediction': prediction,
                'low_confidence': low_confidence,
                'confidence_raw': float(confidence)
            }
            
        except Exception as e:
            print(f"❌ pkl 모델 분석 실패: {e}")
            return None
    
    
    
    def analyze_reviews_batch(self, reviews: List[Dict]) -> List[Dict]:
        """리뷰 목록 일괄 분석"""
        analyzed_reviews = []
        
        for i, review in enumerate(reviews):
            print(f"리뷰 분석 진행 중... ({i+1}/{len(reviews)})")
            
            # 리뷰 텍스트 추출
            review_text = ""
            if 'content' in review:
                review_text = review['content']
            elif 'text' in review:
                review_text = review['text']
            elif 'title' in review:
                review_text = review['title']
            
            # 감정 분석 수행 (평점 정보 포함)
            rating = review.get('rating', 0)
            analysis_result = self.analyze_single_review(review_text, rating)
            
            # 원본 리뷰 데이터와 분석 결과 병합
            analyzed_review = review.copy()
            analyzed_review.update(analysis_result)
            
            analyzed_reviews.append(analyzed_review)
        
        return analyzed_reviews
    
    def get_negative_reviews(self, reviews: List[Dict], confidence_threshold: float = 0.7) -> List[Dict]:
        """부정 리뷰만 필터링"""
        negative_reviews = []
        
        for review in reviews:
            if (review.get('is_negative', False) and 
                review.get('confidence', 0) >= confidence_threshold):
                negative_reviews.append(review)
        
        # 신뢰도순으로 정렬
        negative_reviews.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        return negative_reviews
    
    def get_review_statistics(self, reviews: List[Dict]) -> Dict[str, Any]:
        """리뷰 통계 정보"""
        if not reviews:
            return {
                'total': 0,
                'negative': 0,
                'positive': 0,
                'negative_ratio': 0,
                'positive_ratio': 0,
                'average_confidence': 0
            }
        
        total = len(reviews)
        negative_count = sum(1 for r in reviews if r.get('is_negative', False))
        positive_count = total - negative_count
        
        # 평균 신뢰도 계산
        total_confidence = sum(r.get('confidence', 0) for r in reviews)
        average_confidence = total_confidence / total if total > 0 else 0
        
        return {
            'total': total,
            'negative': negative_count,
            'positive': positive_count,
            'negative_ratio': round((negative_count / total) * 100, 2),
            'positive_ratio': round((positive_count / total) * 100, 2),
            'average_confidence': round(average_confidence * 100, 2)
        }
    
    def get_sentiment_trends(self, reviews: List[Dict]) -> Dict[str, List]:
        """감정 분석 트렌드 (날짜별)"""
        from datetime import datetime
        from collections import defaultdict
        
        daily_sentiments = defaultdict(lambda: {'positive': 0, 'negative': 0})
        
        for review in reviews:
            created_date = review.get('created_date', '')
            if not created_date:
                continue
            
            try:
                # 날짜 형식 파싱
                date_obj = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                date_key = date_obj.strftime('%Y-%m-%d')
                
                if review.get('is_negative', False):
                    daily_sentiments[date_key]['negative'] += 1
                else:
                    daily_sentiments[date_key]['positive'] += 1
                    
            except Exception as e:
                print(f"날짜 파싱 오류: {e}")
                continue
        
        # 정렬된 결과 반환
        sorted_dates = sorted(daily_sentiments.keys())
        
        return {
            'dates': sorted_dates,
            'positive_counts': [daily_sentiments[date]['positive'] for date in sorted_dates],
            'negative_counts': [daily_sentiments[date]['negative'] for date in sorted_dates]
        }
    
    def find_common_negative_keywords(self, negative_reviews: List[Dict], top_n: int = 10) -> List[Dict]:
        """부정 리뷰에서 자주 나오는 키워드 추출"""
        from collections import Counter
        import re
        
        # 한국어 불용어
        stopwords = {
            '이', '그', '저', '것', '들', '의', '가', '을', '를', '에', '와', '과', 
            '도', '만', '하다', '되다', '있다', '없다', '같다', '다', '네', '요',
            '입니다', '습니다', '해요', '해서', '하고', '해도', '했다', '됩니다'
        }
        
        all_words = []
        
        for review in negative_reviews:
            text = review.get('content', '') + ' ' + review.get('title', '')
            
            # 한글만 추출
            words = re.findall(r'[가-힣]+', text)
            
            # 불용어 제거 및 길이 필터링
            filtered_words = [word for word in words 
                            if len(word) >= 2 and word not in stopwords]
            
            all_words.extend(filtered_words)
        
        # 빈도 계산
        word_counts = Counter(all_words)
        
        # 상위 키워드 반환
        top_keywords = []
        for word, count in word_counts.most_common(top_n):
            top_keywords.append({
                'keyword': word,
                'count': count,
                'frequency': round(count / len(negative_reviews), 2)
            })
        
        return top_keywords