"""
리뷰 감정 분석기
"""

from transformers import pipeline
import warnings
from typing import List, Dict, Any
import re

warnings.filterwarnings('ignore')


class ReviewAnalyzer:
    """리뷰 감정 분석 클래스"""
    
    def __init__(self):
        self.sentiment_analyzer = None
        self.load_model()
        
    def load_model(self):
        """감정 분석 모델 로드"""
        try:
            # 한국어 감정 분석에 특화된 모델 사용
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                device=-1
            )
            print("다국어 감정 분석 모델 로드 완료")
        except Exception as e:
            print(f"다국어 모델 로드 실패, 기본 모델 시도: {e}")
            try:
                # 백업으로 기본 모델 사용
                self.sentiment_analyzer = pipeline(
                    "sentiment-analysis",
                    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                    device=-1
                )
                print("영어 감정 분석 모델 로드 완료")
            except Exception as e2:
                print(f"모든 모델 로드 실패: {e2}")
                self.sentiment_analyzer = None
    
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
    
    def analyze_single_review(self, review_text: str) -> Dict[str, Any]:
        """단일 리뷰 감정 분석"""
        try:
            if not review_text or not self.sentiment_analyzer:
                return {
                    'is_negative': False,
                    'confidence': 0,
                    'label': '분석불가',
                    'score': 0,
                    'error': '텍스트가 없거나 모델 로드 실패'
                }
            
            # 텍스트 전처리
            clean_text = self.clean_text(review_text)
            if not clean_text:
                return {
                    'is_negative': False,
                    'confidence': 0,
                    'label': '분석불가',
                    'score': 0,
                    'error': '유효한 텍스트 없음'
                }
            
            # 텍스트 길이 제한 (512자)
            if len(clean_text) > 512:
                clean_text = clean_text[:512]
            
            # 감정 분석 실행
            result = self.sentiment_analyzer(clean_text)[0]
            
            # 결과 해석
            is_negative = self._is_negative_result(result)
            
            return {
                'is_negative': is_negative,
                'confidence': result['score'],
                'label': '부정적' if is_negative else '긍정적',
                'score': round(result['score'] * 100, 2),
                'original_label': result['label']
            }
            
        except Exception as e:
            print(f"리뷰 분석 오류: {e}")
            return {
                'is_negative': False,
                'confidence': 0,
                'label': '분석실패',
                'score': 0,
                'error': str(e)
            }
    
    def _is_negative_result(self, result: Dict) -> bool:
        """분석 결과가 부정적인지 판단"""
        label = result['label'].upper()
        
        # 다양한 모델의 라벨 형식 지원
        negative_labels = [
            'NEGATIVE', 'LABEL_0', 'NEG',
            '1 STAR', '2 STARS',  # 별점 기반
            'DISAPPROVAL', 'ANGER', 'DISGUST'  # 감정 기반
        ]
        
        return label in negative_labels
    
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
            
            # 감정 분석 수행
            analysis_result = self.analyze_single_review(review_text)
            
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