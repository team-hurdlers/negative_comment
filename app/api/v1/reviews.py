from flask import Blueprint, request, jsonify
from app.shared.middlewares.auth import login_required, full_auth_required

reviews_bp = Blueprint('reviews', __name__, url_prefix='/api')

def get_app_globals():
    """app.py의 전역 변수들에 접근"""
    from flask import current_app
    return current_app.config.get('app_globals', {})

# ===== 카페24 API 리뷰 관련 엔드포인트 =====

@reviews_bp.route('/reviews/latest')
@login_required
def get_latest_reviews():
    """최신 리뷰 조회"""
    try:
        app_globals = get_app_globals()
        review_api = app_globals.get('review_api')
        
        # 카페24 API 인증 체크
        if not review_api:
            return jsonify({'error': '카페24 API 인증이 필요합니다.', 'cafe24_auth_required': True}), 401
            
        days = request.args.get('days', 7, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        reviews = review_api.get_latest_reviews(days=days, limit=limit)
        
        # 감정 분석 수행 - app.py 함수들 사용
        from flask import current_app
        analyze_reviews_batch = current_app.config.get('analyze_reviews_batch')
        enrich_reviews_with_product_names = current_app.config.get('enrich_reviews_with_product_names')
        get_review_statistics = current_app.config.get('get_review_statistics')
        get_negative_reviews = current_app.config.get('get_negative_reviews')
        
        if reviews:
            analyzed_reviews = analyze_reviews_batch(reviews) if analyze_reviews_batch else reviews
            # 상품명 추가
            enriched_reviews = enrich_reviews_with_product_names(analyzed_reviews) if enrich_reviews_with_product_names else analyzed_reviews
            statistics = get_review_statistics(enriched_reviews) if get_review_statistics else {}
            negative_reviews = get_negative_reviews(enriched_reviews) if get_negative_reviews else []
            
            return jsonify({
                'reviews': enriched_reviews,
                'statistics': statistics,
                'negative_reviews': negative_reviews[:10],  # 상위 10개
                'count': len(enriched_reviews)
            })
        else:
            return jsonify({
                'reviews': [],
                'statistics': get_review_statistics([]) if get_review_statistics else {},
                'negative_reviews': [],
                'count': 0
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@reviews_bp.route('/products')
@full_auth_required
def get_products():
    """상품 목록 조회"""
    try:
        app_globals = get_app_globals()
        review_api = app_globals.get('review_api')
        
        limit = request.args.get('limit', 100, type=int)
        
        products = review_api.get_products(limit=limit)
        
        return jsonify({
            'products': products,
            'count': len(products)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500