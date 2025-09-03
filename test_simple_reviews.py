#!/usr/bin/env python3
"""
간단한 리뷰 조회 테스트
상세 조회 없이 목록만 가져와서 텍스트 길이 확인
"""

import json
import sys
import os
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auth.cafe24_oauth import Cafe24OAuth
from utils.config_manager import ConfigManager
import requests
import time

def test_simple_reviews():
    """간단한 리뷰 조회 테스트"""
    
    print("=" * 60)
    print("간단한 리뷰 조회 테스트")
    print("=" * 60)
    
    # 설정 및 API 초기화
    config = ConfigManager()
    
    if not config.is_cafe24_configured():
        print("❌ 카페24 설정이 필요합니다.")
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
            return
        
        base_url = f"https://{cafe24_config['mall_id']}.cafe24api.com/api/v2"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'X-Cafe24-Api-Version': '2025-06-01'
        }
        
        print()
        
        # 1. 게시판 목록 조회
        print("📋 게시판 목록 조회 중...")
        boards_response = requests.get(f"{base_url}/admin/boards", headers=headers)
        boards_response.raise_for_status()
        boards_data = boards_response.json()
        
        boards = boards_data.get('boards', [])
        print(f"전체 게시판: {len(boards)}개")
        
        # 리뷰 게시판 찾기
        review_boards = []
        for board in boards:
            board_name = board.get('board_name', '').lower()
            if any(keyword in board_name for keyword in ['review', '리뷰', '후기', '평가']):
                review_boards.append(board)
        
        print(f"리뷰 게시판: {len(review_boards)}개")
        for board in review_boards:
            print(f"  - {board['board_name']} (번호: {board['board_no']})")
        
        if not review_boards:
            print("❌ 리뷰 게시판을 찾을 수 없습니다.")
            return
        
        print()
        
        # 2. 첫 번째 리뷰 게시판에서 게시글 조회
        board = review_boards[0]
        board_no = board['board_no']
        print(f"📝 게시판 '{board['board_name']}'에서 게시글 조회 중...")
        
        # 필드를 명시하여 요청
        params = {
            'limit': 5,
            'fields': 'article_no,title,content,writer,created_date,product_no,rating'
        }
        
        articles_response = requests.get(
            f"{base_url}/admin/boards/{board_no}/articles", 
            headers=headers, 
            params=params
        )
        articles_response.raise_for_status()
        articles_data = articles_response.json()
        
        articles = articles_data.get('articles', [])
        print(f"조회된 게시글: {len(articles)}개")
        print()
        
        # 각 게시글의 내용 길이 분석
        results = []
        
        for i, article in enumerate(articles, 1):
            print(f"--- 게시글 #{i} ---")
            print(f"게시글 번호: {article.get('article_no', 'N/A')}")
            print(f"작성자: {article.get('writer', 'N/A')}")
            print(f"작성일: {article.get('created_date', 'N/A')}")
            print(f"상품번호: {article.get('product_no', 'N/A')}")
            print(f"평점: {article.get('rating', 'N/A')}")
            
            title = article.get('title', '')
            content = article.get('content', '')
            
            print(f"제목 길이: {len(title)}자")
            print(f"내용 길이: {len(content)}자")
            
            print(f"제목: '{title}'")
            print(f"내용: '{content}'")
            
            # 결과 저장
            result = {
                'article_no': article.get('article_no'),
                'writer': article.get('writer', 'N/A'),
                'created_date': article.get('created_date', 'N/A'),
                'product_no': article.get('product_no', 'N/A'),
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
        
        if results:
            title_lengths = [r['title_length'] for r in results]
            content_lengths = [r['content_length'] for r in results]
            full_lengths = [r['full_length'] for r in results]
            
            print(f"제목 길이 - 평균: {sum(title_lengths)/len(title_lengths):.1f}자, 최대: {max(title_lengths)}자, 최소: {min(title_lengths)}자")
            print(f"내용 길이 - 평균: {sum(content_lengths)/len(content_lengths):.1f}자, 최대: {max(content_lengths)}자, 최소: {min(content_lengths)}자")
            print(f"전체 길이 - 평균: {sum(full_lengths)/len(full_lengths):.1f}자, 최대: {max(full_lengths)}자, 최소: {min(full_lengths)}자")
            
            # 10자 이하인 항목 체크
            short_contents = [r for r in results if r['content_length'] <= 30]
            if short_contents:
                print(f"\n⚠️  내용이 30자 이하인 리뷰: {len(short_contents)}개")
                for r in short_contents:
                    print(f"   게시글 #{r['article_no']}: '{r['content']}'")
            
            # 결과를 JSON 파일로 저장
            output_file = f"simple_review_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'test_date': datetime.now().isoformat(),
                        'board_info': {
                            'board_no': str(board_no),
                            'board_name': str(board['board_name'])
                        },
                        'total_articles': len(results),
                        'statistics': {
                            'title_avg_length': sum(title_lengths)/len(title_lengths),
                            'content_avg_length': sum(content_lengths)/len(content_lengths),
                            'full_avg_length': sum(full_lengths)/len(full_lengths),
                            'title_max_length': max(title_lengths),
                            'content_max_length': max(content_lengths),
                            'full_max_length': max(full_lengths),
                            'short_content_count': len(short_contents)
                        },
                        'articles': results
                    }, ensure_ascii=False, indent=2)
            except Exception as json_error:
                print(f"⚠️  JSON 저장 오류: {json_error}")
                print("결과는 출력되었지만 파일 저장에 실패했습니다.")
            
            print(f"\n💾 결과가 '{output_file}' 파일로 저장되었습니다.")
        else:
            print("❌ 분석할 게시글이 없습니다.")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_reviews()