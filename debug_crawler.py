#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from crawler import ShoppingMallCrawler

def debug_crawler():
    """디버그 모드로 크롤러 테스트"""
    crawler = ShoppingMallCrawler()
    url = 'https://dentistestore.kr/board/review/list.html?board_no=4'
    
    print("🔍 디버그 모드로 크롤링 시작...")
    print(f"URL: {url}")
    print("="*80)
    
    # 디버그 모드로 1페이지만 크롤링
    reviews = crawler.crawl_dentiste_board(url, max_pages=1, debug=True)
    
    print("="*80)
    print(f"🎯 최종 결과: {len(reviews)}개 고유 리뷰")
    
    if reviews:
        print("\n📝 최종 리뷰 목록:")
        for i, review in enumerate(reviews, 1):
            print(f"{i}. [{review.get('page', '?')}페이지] {review['text']}")
            if review.get('date'):
                print(f"   날짜: {review['date']}")
    
    return reviews

if __name__ == "__main__":
    debug_crawler()