#!/usr/bin/env python3
"""
리뷰 내용 전체 조회 테스트
카페24 API에서 실제로 얼마나 긴 텍스트가 오는지 확인
"""

import json
import sys
import os
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.cafe24_reviews import Cafe24ReviewAPI
from utils.config_manager import ConfigManager
from auth.cafe24_oauth import Cafe24OAuth

def test_review_content():
    """리뷰 내용 길이 테스트"""
    
    print("=" * 60)
    print("리뷰 내용 전체 조회 테스트")
    print("=" * 60)
    
    # 설정 및 API 초기화
    config = ConfigManager()
    
    if not config.is_cafe24_configured():
        print("❌ 카페24 설정이 필요합니다.")
        print("config.json 파일을 확인하세요.")
        return
    
    cafe24_config = config.get_cafe24_config()
    
    try:
        # OAuth 클라이언트 초기화
        oauth_client = Cafe24OAuth(
            client_id=cafe24_config['client_id'],
            client_secret=cafe24_config['client_secret'],
            mall_id=cafe24_config['mall_id'],
            redirect_uri=cafe24_config.get('redirect_uri', '')
        )
        
        print(f"🏪 Mall ID: {cafe24_config['mall_id']}")
        
        # 유효한 토큰 가져오기
        try:
            access_token = oauth_client.get_valid_token()
            print("✅ 유효한 토큰을 가져왔습니다.")
            print(f"🔑 Access Token: {access_token[:20]}...")
        except Exception as e:
            print(f"❌ 토큰 가져오기 실패: {e}")
            print("웹 브라우저에서 OAuth 인증을 먼저 완료하세요.")
            return
        
        # 카페24 API 초기화
        api = Cafe24ReviewAPI(oauth_client)
        
        print()
        
        # 최신 리뷰 5개만 가져와서 테스트
        print("📝 최신 리뷰 5개 조회 중...")
        reviews = api.get_latest_reviews(days=30, limit=5)
        
        if not reviews:
            print("❌ 리뷰를 찾을 수 없습니다.")
            return
        
        print(f"✅ {len(reviews)}개의 리뷰를 찾았습니다.")
        print()
        
        # 각 리뷰의 내용 길이 분석
        results = []
        
        for i, review in enumerate(reviews, 1):
            print(f"--- 리뷰 #{i} ---")
            print(f"작성자: {review.get('writer', 'N/A')}")
            print(f"작성일: {review.get('created_date', 'N/A')}")
            print(f"상품번호: {review.get('product_no', 'N/A')}")
            
            title = review.get('title', '')
            content = review.get('content', '')
            
            print(f"제목 길이: {len(title)}자")
            print(f"내용 길이: {len(content)}자")
            
            print(f"제목: '{title}'")
            print(f"내용 (처음 200자): '{content[:200]}{'...' if len(content) > 200 else ''}'")
            
            # 결과 저장
            result = {
                'review_number': i,
                'writer': review.get('writer', 'N/A'),
                'created_date': review.get('created_date', 'N/A'),
                'product_no': review.get('product_no', 'N/A'),
                'title': title,
                'title_length': len(title),
                'content': content,
                'content_length': len(content),
                'full_text': f"{title} {content}".strip(),
                'full_length': len(f"{title} {content}".strip())
            }
            results.append(result)
            
            print()
        
        # 통계 출력
        print("=" * 60)
        print("📊 통계 정보")
        print("=" * 60)
        
        title_lengths = [r['title_length'] for r in results]
        content_lengths = [r['content_length'] for r in results]
        full_lengths = [r['full_length'] for r in results]
        
        print(f"제목 길이 - 평균: {sum(title_lengths)/len(title_lengths):.1f}자, 최대: {max(title_lengths)}자, 최소: {min(title_lengths)}자")
        print(f"내용 길이 - 평균: {sum(content_lengths)/len(content_lengths):.1f}자, 최대: {max(content_lengths)}자, 최소: {min(content_lengths)}자")
        print(f"전체 길이 - 평균: {sum(full_lengths)/len(full_lengths):.1f}자, 최대: {max(full_lengths)}자, 최소: {min(full_lengths)}자")
        
        # 10자 이하인 항목 체크
        short_contents = [r for r in results if r['content_length'] <= 10]
        if short_contents:
            print(f"\n⚠️  내용이 10자 이하인 리뷰: {len(short_contents)}개")
            for r in short_contents:
                print(f"   리뷰 #{r['review_number']}: '{r['content']}'")
        
        # 결과를 JSON 파일로 저장
        output_file = f"review_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_date': datetime.now().isoformat(),
                'total_reviews': len(results),
                'statistics': {
                    'title_avg_length': sum(title_lengths)/len(title_lengths),
                    'content_avg_length': sum(content_lengths)/len(content_lengths),
                    'full_avg_length': sum(full_lengths)/len(full_lengths),
                    'title_max_length': max(title_lengths),
                    'content_max_length': max(content_lengths),
                    'full_max_length': max(full_lengths),
                    'short_content_count': len(short_contents)
                },
                'reviews': results
            }, ensure_ascii=False, indent=2)
        
        print(f"\n💾 결과가 '{output_file}' 파일로 저장되었습니다.")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_review_content()