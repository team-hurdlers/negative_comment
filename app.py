from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from transformers import pipeline
from crawler import ShoppingMallCrawler
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)
CORS(app)

sentiment_analyzer = None
crawler = ShoppingMallCrawler()

def load_model():
    global sentiment_analyzer
    try:
        sentiment_analyzer = pipeline(
            "sentiment-analysis",
            model="beomi/kcbert-base",
            device=-1
        )
        print("모델 로드 완료")
    except Exception as e:
        print(f"모델 로드 실패: {e}")
        sentiment_analyzer = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': '텍스트를 입력해주세요.'}), 400
        
        if sentiment_analyzer is None:
            load_model()
            
        if sentiment_analyzer is None:
            return jsonify({'error': '모델 로드 실패'}), 500
        
        result = sentiment_analyzer(text[:512])[0]
        
        is_negative = False
        confidence = result['score']
        
        if result['label'] == 'NEGATIVE' or result['label'] == 'LABEL_0':
            is_negative = True
        elif result['label'] == 'POSITIVE' or result['label'] == 'LABEL_1':
            is_negative = False
        
        response = {
            'text': text,
            'is_negative': is_negative,
            'confidence': confidence,
            'label': '부정적' if is_negative else '긍정적',
            'score': round(confidence * 100, 2)
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/batch_analyze', methods=['POST'])
def batch_analyze():
    try:
        data = request.json
        texts = data.get('texts', [])
        
        if not texts:
            return jsonify({'error': '텍스트 리스트를 입력해주세요.'}), 400
        
        if sentiment_analyzer is None:
            load_model()
            
        if sentiment_analyzer is None:
            return jsonify({'error': '모델 로드 실패'}), 500
        
        results = []
        for text in texts:
            if text:
                result = sentiment_analyzer(text[:512])[0]
                is_negative = result['label'] in ['NEGATIVE', 'LABEL_0']
                results.append({
                    'text': text,
                    'is_negative': is_negative,
                    'confidence': result['score'],
                    'label': '부정적' if is_negative else '긍정적',
                    'score': round(result['score'] * 100, 2)
                })
        
        negative_count = sum(1 for r in results if r['is_negative'])
        positive_count = len(results) - negative_count
        
        return jsonify({
            'results': results,
            'summary': {
                'total': len(results),
                'negative': negative_count,
                'positive': positive_count,
                'negative_ratio': round((negative_count / len(results)) * 100, 2) if results else 0
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/crawl_and_analyze', methods=['POST'])
def crawl_and_analyze():
    """URL에서 리뷰를 크롤링하고 분석"""
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({'error': 'URL을 입력해주세요.'}), 400
        
        # 제품 정보 추출
        product_info = crawler.extract_product_info(url)
        
        # 리뷰 크롤링
        reviews = crawler.crawl_reviews(url)
        
        if not reviews:
            return jsonify({'error': '리뷰를 찾을 수 없습니다.'}), 404
        
        if sentiment_analyzer is None:
            load_model()
            
        if sentiment_analyzer is None:
            return jsonify({'error': '모델 로드 실패'}), 500
        
        # 각 리뷰 분석
        analyzed_reviews = []
        for review in reviews:
            if review['text']:
                result = sentiment_analyzer(review['text'][:512])[0]
                is_negative = result['label'] in ['NEGATIVE', 'LABEL_0']
                
                analyzed_reviews.append({
                    'text': review['text'],
                    'is_negative': is_negative,
                    'confidence': result['score'],
                    'label': '부정적' if is_negative else '긍정적',
                    'score': round(result['score'] * 100, 2),
                    'rating': review.get('rating', 0)
                })
        
        # 통계 계산
        negative_reviews = [r for r in analyzed_reviews if r['is_negative']]
        positive_reviews = [r for r in analyzed_reviews if not r['is_negative']]
        
        response = {
            'product': product_info,
            'reviews': analyzed_reviews,
            'summary': {
                'total': len(analyzed_reviews),
                'negative': len(negative_reviews),
                'positive': len(positive_reviews),
                'negative_ratio': round((len(negative_reviews) / len(analyzed_reviews)) * 100, 2) if analyzed_reviews else 0
            },
            'top_negative': negative_reviews[:5],  # 상위 5개 부정 리뷰
            'top_positive': positive_reviews[:5]   # 상위 5개 긍정 리뷰
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("서버 시작 중...")
    load_model()
    app.run(debug=True, port=5000)