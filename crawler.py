import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re
from urllib.parse import urlparse

class ShoppingMallCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        return webdriver.Chrome(options=chrome_options)
    
    def detect_mall_type(self, url):
        """URL을 기반으로 쇼핑몰 타입 감지"""
        domain = urlparse(url).netloc.lower()
        
        if 'coupang.com' in domain:
            return 'coupang'
        elif 'naver.com' in domain or 'smartstore' in domain:
            return 'naver'
        elif '11st.co.kr' in domain:
            return '11st'
        elif 'gmarket.co.kr' in domain:
            return 'gmarket'
        elif 'auction.co.kr' in domain:
            return 'auction'
        elif 'interpark.com' in domain:
            return 'interpark'
        else:
            return 'generic'
    
    def crawl_coupang(self, url):
        """쿠팡 리뷰 크롤링"""
        reviews = []
        try:
            driver = self.setup_driver()
            driver.get(url)
            time.sleep(3)
            
            # 리뷰 탭 클릭
            try:
                review_tab = driver.find_element(By.CSS_SELECTOR, '[data-tab="review"]')
                review_tab.click()
                time.sleep(2)
            except:
                pass
            
            # 리뷰 수집
            review_elements = driver.find_elements(By.CSS_SELECTOR, '.sdp-review__article__list__review')
            
            for element in review_elements[:50]:  # 최대 50개 리뷰
                try:
                    text = element.find_element(By.CSS_SELECTOR, '.sdp-review__article__list__review__content').text
                    rating = len(element.find_elements(By.CSS_SELECTOR, '.sdp-review__article__list__star--active'))
                    
                    reviews.append({
                        'text': text.strip(),
                        'rating': rating,
                        'source': 'coupang'
                    })
                except:
                    continue
                    
            driver.quit()
        except Exception as e:
            print(f"Coupang crawling error: {e}")
            
        return reviews
    
    def crawl_naver(self, url):
        """네이버 쇼핑 리뷰 크롤링"""
        reviews = []
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 네이버 스마트스토어 리뷰
            review_elements = soup.find_all('div', class_='review_text')
            
            for element in review_elements[:50]:
                try:
                    text = element.get_text(strip=True)
                    reviews.append({
                        'text': text,
                        'rating': 0,  # 별점은 별도 처리 필요
                        'source': 'naver'
                    })
                except:
                    continue
                    
        except Exception as e:
            print(f"Naver crawling error: {e}")
            
        return reviews
    
    def crawl_11st(self, url):
        """11번가 리뷰 크롤링"""
        reviews = []
        try:
            driver = self.setup_driver()
            driver.get(url)
            time.sleep(3)
            
            # 리뷰 섹션으로 스크롤
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            
            # 리뷰 수집
            review_elements = driver.find_elements(By.CSS_SELECTOR, '.review_list_element')
            
            for element in review_elements[:50]:
                try:
                    text = element.find_element(By.CSS_SELECTOR, '.cont_text').text
                    reviews.append({
                        'text': text.strip(),
                        'rating': 0,
                        'source': '11st'
                    })
                except:
                    continue
                    
            driver.quit()
        except Exception as e:
            print(f"11st crawling error: {e}")
            
        return reviews
    
    def crawl_generic(self, url):
        """일반 웹페이지에서 리뷰 추출"""
        reviews = []
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 일반적인 리뷰 패턴 찾기
            review_patterns = [
                'review', 'comment', '리뷰', '후기', '평가',
                'feedback', 'testimonial', '댓글'
            ]
            
            for pattern in review_patterns:
                # class나 id에 패턴이 포함된 요소 찾기
                elements = soup.find_all(attrs={
                    'class': re.compile(pattern, re.I)
                }) + soup.find_all(attrs={
                    'id': re.compile(pattern, re.I)
                })
                
                for element in elements[:50]:
                    text = element.get_text(strip=True)
                    if len(text) > 10 and len(text) < 1000:  # 적절한 길이의 텍스트만
                        reviews.append({
                            'text': text,
                            'rating': 0,
                            'source': 'generic'
                        })
            
            # 중복 제거
            seen = set()
            unique_reviews = []
            for review in reviews:
                if review['text'] not in seen:
                    seen.add(review['text'])
                    unique_reviews.append(review)
            
            return unique_reviews[:50]
            
        except Exception as e:
            print(f"Generic crawling error: {e}")
            
        return reviews
    
    def crawl_reviews(self, url):
        """URL에 따라 적절한 크롤러 선택"""
        mall_type = self.detect_mall_type(url)
        
        print(f"Detected mall type: {mall_type}")
        
        if mall_type == 'coupang':
            return self.crawl_coupang(url)
        elif mall_type == 'naver':
            return self.crawl_naver(url)
        elif mall_type == '11st':
            return self.crawl_11st(url)
        else:
            return self.crawl_generic(url)
    
    def extract_product_info(self, url):
        """제품 정보 추출"""
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 제품명 추출 시도
            title = None
            title_selectors = [
                'h1', 'h2',
                {'class': re.compile('product.*title', re.I)},
                {'class': re.compile('item.*name', re.I)},
                {'id': re.compile('product.*title', re.I)}
            ]
            
            for selector in title_selectors:
                if isinstance(selector, dict):
                    element = soup.find(attrs=selector)
                else:
                    element = soup.find(selector)
                    
                if element:
                    title = element.get_text(strip=True)
                    break
            
            # 가격 추출 시도
            price = None
            price_selectors = [
                {'class': re.compile('price', re.I)},
                {'class': re.compile('cost', re.I)},
                {'class': re.compile('amount', re.I)}
            ]
            
            for selector in price_selectors:
                element = soup.find(attrs=selector)
                if element:
                    price_text = element.get_text(strip=True)
                    # 숫자만 추출
                    price_match = re.search(r'[\d,]+', price_text)
                    if price_match:
                        price = price_match.group()
                        break
            
            return {
                'title': title or 'Unknown Product',
                'price': price,
                'url': url
            }
            
        except Exception as e:
            print(f"Product info extraction error: {e}")
            return {
                'title': 'Unknown Product',
                'price': None,
                'url': url
            }