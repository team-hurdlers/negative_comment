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
        elif 'dentistestore.kr' in domain:
            # 게시판 URL과 제품 URL 구분
            if '/board/review' in url:
                return 'dentiste_board'
            else:
                return 'dentiste'
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
    
    def crawl_dentiste(self, url):
        """덴티스테 스토어 리뷰 크롤링"""
        reviews = []
        driver = None
        
        try:
            driver = self.setup_driver()
            
            # 모든 페이지 순회 (1페이지부터 44페이지까지)
            for page_num in range(1, 45):  # 44페이지까지
                try:
                    # 각 페이지 URL 생성 (덴티스테는 page_4 파라미터 사용)
                    if page_num == 1:
                        page_url = url
                    else:
                        # URL에 page_4 파라미터 추가
                        separator = '&' if '?' in url else '?'
                        page_url = f"{url}{separator}page_4={page_num}#prdReview"
                    
                    print(f"Dentiste: 페이지 {page_num} 크롤링 중... ({page_url})")
                    
                    driver.get(page_url)
                    time.sleep(3)
                    
                    # 리뷰 섹션으로 스크롤
                    try:
                        review_section = driver.find_element(By.CSS_SELECTOR, '.prdReview')
                        driver.execute_script("arguments[0].scrollIntoView();", review_section)
                        time.sleep(2)
                    except:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                    
                    # 페이지 소스에서 리뷰 추출
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # 리뷰 섹션 찾기
                    review_section = soup.find(class_='prdReview') or soup.find(id='prdReview')
                    if not review_section:
                        print(f"Dentiste: 페이지 {page_num}에서 리뷰 섹션을 찾을 수 없음")
                        continue
                    
                    # 리뷰 아이템들 찾기
                    review_items = review_section.find_all('li')
                    page_reviews = 0
                    
                    for item in review_items:
                        try:
                            item_text = item.get_text(strip=True)
                            
                            # 다양한 패턴으로 리뷰 텍스트 추출
                            extracted_reviews = self._extract_dentiste_review_text(item_text)
                            
                            for review_text in extracted_reviews:
                                if self._is_valid_dentiste_review(review_text):
                                    reviews.append({
                                        'text': review_text,
                                        'rating': 5,  # 대부분 5점 리뷰
                                        'source': 'dentiste'
                                    })
                                    page_reviews += 1
                        
                        except Exception as item_error:
                            continue
                    
                    print(f"Dentiste: 페이지 {page_num}에서 {page_reviews}개 리뷰 수집")
                    
                    # 리뷰가 없으면 크롤링 종료
                    if page_reviews == 0:
                        print(f"Dentiste: 페이지 {page_num}에서 리뷰를 찾을 수 없어 크롤링 종료")
                        break
                
                except Exception as page_error:
                    print(f"Dentiste: 페이지 {page_num} 처리 오류 - {page_error}")
                    continue
            
            # 중복 제거
            seen = set()
            unique_reviews = []
            for review in reviews:
                if review['text'] not in seen:
                    seen.add(review['text'])
                    unique_reviews.append(review)
            
            print(f"Dentiste: 총 {len(unique_reviews)}개 고유 리뷰 수집 완료")
            return unique_reviews
            
        except Exception as e:
            print(f"Dentiste crawling error: {e}")
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
        return reviews
    
    def _extract_dentiste_review_text(self, item_text):
        """덴티스테 리뷰에서 텍스트 추출"""
        extracted = []
        
        # 패턴 1: 모든 별점 다음의 텍스트 (5.0, 4.0, 3.0, 2.0, 1.0)
        pattern1 = r'[1-5]\.0\s+([가-힣\s\.\?!:]{5,200}?)(?=\s*더보기|$|이\*+|\d{2}\.\d{2}\.\d{2}|조회|신고)'
        matches1 = re.findall(pattern1, item_text)
        extracted.extend(matches1)
        
        # 패턴 2: 이모지가 포함된 리뷰
        pattern2 = r'([가-힣\s\.\?!:]{5,200}[😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉][😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉]*)'
        matches2 = re.findall(pattern2, item_text)
        extracted.extend(matches2)
        
        # 패턴 3: 긍정적 감정 표현이 있는 텍스트
        pattern3 = r'([가-힣\s\.\?!:]{5,200}(?:좋아요|좋네요|맛있|추천|만족|기분이 좋|잘 산|너무 좋|편해요|깔끔|청결|최고|감사|빨라요)[가-힣\s!.]{0,50})'
        matches3 = re.findall(pattern3, item_text)
        extracted.extend(matches3)
        
        # 패턴 4: 부정적 감정 표현이 있는 텍스트 (NEW!)
        pattern4 = r'([가-힣\s\.\?!:]{5,200}(?:비싸요|깨져|터져|문제|불편|실망|아쉬|후회|별로|안.*좋|나빠|잘못|확인|제발|죄송|배송|포장)[가-힣\s!.]{0,50})'
        matches4 = re.findall(pattern4, item_text)
        extracted.extend(matches4)
        
        # 패턴 5: 날짜 앞의 일반적인 한글 리뷰
        pattern5 = r'(\d{4}-\d{2}-\d{2})\s+([가-힣\s\.\?!:]{10,200}?)(?=\s*더보기|$|신고|차단)'
        matches5 = re.findall(pattern5, item_text)
        for match in matches5:
            extracted.append(match[1])  # 날짜는 제외하고 텍스트만
        
        # 패턴 6: 일반적인 리뷰 패턴 (특수문자 포함)
        pattern6 = r'([가-힣\s\.\?!:]{10,200}?)(?=\s*더보기|$|이\*+|\d{2}\.\d{2}\.\d{2}|신고|차단)'
        matches6 = re.findall(pattern6, item_text)
        extracted.extend(matches6)
        
        # 중복 제거 및 정리
        cleaned = []
        for text in extracted:
            text = text.strip()
            if text and len(text) >= 5 and len(text) <= 500:
                # 의미있는 내용인지 확인
                if re.search(r'[가-힣]{3,}', text):  # 최소 3글자 이상 한글 포함
                    cleaned.append(text)
        
        return list(set(cleaned))
    
    def _is_valid_dentiste_review(self, text):
        """덴티스테 리뷰가 유효한지 확인"""
        if not text or len(text) < 5 or len(text) > 500:
            return False
        
        # 제외할 패턴들 (시스템 메시지나 공지사항)
        exclude_patterns = [
            r'이용자에게 책임',
            r'상품구매안내',
            r'결제.*안내',
            r'카드사에서',
            r'임의로 주문',
            r'재화.*공급',
            r'휴대용.*현재.*위치',
            r'홈.*상품.*관심상품',
            r'카카오톡.*라인.*밴드',
            r'타인 명의',
            r'도난 카드',
            r'고액결제',
            r'정상적인 주문',
            r'조회\s*\d+$',
            r'^\d+$',
            r'^[1-5]\.0$',
            r'더보기\s*>$',
            r'^신고.*차단$',
            r'덴티스테공식스토어',
            r'고객센터로 연락주세요',
            r'100%만족을 추구하는'
        ]
        
        for pattern in exclude_patterns:
            if re.search(pattern, text):
                return False
        
        # 리뷰다운 패턴이 있는지 확인 (긍정/부정 모두 포함)
        review_indicators = [
            r'[😀😊👍❤️💕😄😍🥰😎🙂☺️]',  # 이모지
            r'좋아요|좋네요|맛있|추천|만족|기분|잘.*산|너무.*좋|편해요|깔끔|청결|빨라요',  # 긍정적 표현
            r'비싸요|깨져|터져|문제|불편|실망|아쉬|후회|별로|안.*좋|나빠|잘못|확인.*안하시나요|제발',  # 부정적 표현
            r'사용|구매|배송|포장|제품|상품|뚜껑|박스|호수|배송지',  # 일반적인 리뷰 용어
            r'좀.*더|하나가|중.*하나|어떻게|왜|언제|어디|뭐|누구'  # 질문/불만 표현
        ]
        
        # 최소한 하나의 리뷰 패턴이 있어야 함
        has_review_indicator = any(re.search(pattern, text) for pattern in review_indicators)
        
        # 너무 짧거나 의미없는 텍스트 제외
        if len(text.strip()) < 8:
            return False
            
        # 한글이 포함되어야 함
        if not re.search(r'[가-힣]{2,}', text):
            return False
        
        return has_review_indicator
    
    def _is_valid_review(self, text):
        """유효한 리뷰인지 확인"""
        if not text or len(text) < 5 or len(text) > 200:
            return False
        
        # 제외할 패턴들
        exclude_patterns = [
            r'이용자에게 책임',
            r'상품구매안내',
            r'결제.*안내',
            r'배송.*지역',
            r'카드사에서',
            r'확인전화',
            r'임의로 주문',
            r'재화.*공급',
            r'휴대용.*현재.*위치',
            r'홈.*상품.*관심상품',
            r'카카오톡.*라인.*밴드',
            r'안전을 위해',
            r'타인 명의',
            r'도난 카드',
            r'판단될 경우',
            r'소요될 수 있으며',
            r'택배사의 사정',
            r'지연될 수 있습니다',
            r'서면을 받은',
            r'시작된 날부터',
            r'고액결제',
            r'정상적인 주문',
        ]
        
        for pattern in exclude_patterns:
            if re.search(pattern, text):
                return False
        
        # 리뷰다운 패턴이 있는지 확인
        review_indicators = [
            r'[😀😊👍❤️💕😄😍🥰]',  # 이모지
            r'좋아요|좋네요|맛있|추천|만족|기분|잘.*산',  # 긍정적 표현
            r'별로|실망|아쉬|불만|후회',  # 부정적 표현
        ]
        
        has_review_indicator = any(re.search(pattern, text) for pattern in review_indicators)
        
        return has_review_indicator
    
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
    
    def crawl_dentiste_board(self, url, max_pages=3, full_analysis=False, debug=False):
        """덴티스테 리뷰 게시판 크롤링 (신규 리뷰 확인용)"""
        reviews = []
        driver = None
        
        try:
            driver = self.setup_driver()
            
            print(f"Dentiste Board: 게시판 크롤링 시작 - {url}")
            
            # 최근 몇 페이지만 확인 (신규 리뷰 모니터링용)
            for page_num in range(1, max_pages + 1):
                try:
                    # 페이지 URL 생성
                    if page_num == 1:
                        page_url = url
                    else:
                        separator = '&' if '?' in url else '?'
                        page_url = f"{url}{separator}page={page_num}"
                    
                    print(f"Dentiste Board: 페이지 {page_num} 크롤링 중...")
                    
                    driver.get(page_url)
                    time.sleep(3)
                    
                    # "더보기" 버튼들을 모두 클릭해서 전체 리뷰 내용 확장
                    try:
                        more_buttons = driver.find_elements(By.XPATH, "//a[contains(text(), '더보기')]")
                        if debug:
                            print(f"더보기 버튼 {len(more_buttons)}개 발견")
                        
                        for i, button in enumerate(more_buttons[:10]):  # 최대 10개만 클릭
                            try:
                                if button.is_displayed():
                                    driver.execute_script("arguments[0].click();", button)
                                    time.sleep(0.5)  # 짧은 대기
                                    if debug:
                                        print(f"더보기 버튼 {i+1} 클릭 완료")
                            except Exception as click_error:
                                if debug:
                                    print(f"더보기 버튼 {i+1} 클릭 실패: {click_error}")
                                continue
                        
                        # 모든 더보기 클릭 후 잠시 대기
                        time.sleep(2)
                        
                    except Exception as expand_error:
                        if debug:
                            print(f"더보기 확장 오류: {expand_error}")
                    
                    # 확장된 페이지 소스에서 리뷰 추출
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # 리뷰 리스트 찾기
                    review_items = soup.find_all('li')
                    page_reviews = 0
                    
                    for i, item in enumerate(review_items):
                        try:
                            item_text = item.get_text(strip=True)
                            
                            if debug and item_text and len(item_text) > 10:
                                print(f"\n--- 아이템 {i+1} (페이지 {page_num}) ---")
                                print(f"원본 텍스트: {item_text[:200]}...")
                            
                            # 게시판 스타일 리뷰 텍스트 추출
                            extracted_reviews = self._extract_board_review_text(item_text)
                            
                            if debug and extracted_reviews:
                                print(f"추출된 리뷰들: {len(extracted_reviews)}개")
                                for j, extracted in enumerate(extracted_reviews):
                                    print(f"  {j+1}. '{extracted}'")
                            
                            for review_text in extracted_reviews:
                                is_valid = self._is_valid_board_review(review_text)
                                
                                if debug:
                                    print(f"  → 유효성 검사: {'✅ 통과' if is_valid else '❌ 실패'}")
                                
                                if is_valid:
                                    # 날짜 추출 시도
                                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', item_text)
                                    review_date = date_match.group(1) if date_match else None
                                    
                                    reviews.append({
                                        'text': review_text,
                                        'rating': 5,  # 게시판에서는 대부분 긍정적
                                        'source': 'dentiste_board',
                                        'date': review_date,
                                        'page': page_num
                                    })
                                    page_reviews += 1
                        
                        except Exception as item_error:
                            if debug:
                                print(f"아이템 처리 오류: {item_error}")
                            continue
                    
                    print(f"Dentiste Board: 페이지 {page_num}에서 {page_reviews}개 리뷰 수집")
                    
                    # 리뷰가 없으면 더 이상 진행하지 않음
                    if page_reviews == 0:
                        print(f"Dentiste Board: 페이지 {page_num}에서 리뷰를 찾을 수 없어 크롤링 종료")
                        break
                
                except Exception as page_error:
                    print(f"Dentiste Board: 페이지 {page_num} 처리 오류 - {page_error}")
                    continue
            
            # 중복 제거
            seen = set()
            unique_reviews = []
            duplicates = []
            
            for review in reviews:
                if review['text'] not in seen:
                    seen.add(review['text'])
                    unique_reviews.append(review)
                else:
                    duplicates.append(review)
            
            if debug:
                print(f"\n=== 중복 제거 결과 ===")
                print(f"총 수집: {len(reviews)}개")
                print(f"고유 리뷰: {len(unique_reviews)}개")
                print(f"중복 리뷰: {len(duplicates)}개")
                
                if duplicates:
                    print(f"\n중복된 리뷰들:")
                    dup_texts = {}
                    for dup in duplicates:
                        text = dup['text'][:50] + "..."
                        dup_texts[text] = dup_texts.get(text, 0) + 1
                    
                    for text, count in dup_texts.items():
                        print(f"  '{text}' - {count}번 중복")
                
                print(f"\n고유 리뷰 목록:")
                for i, review in enumerate(unique_reviews, 1):
                    print(f"  {i}. [{review.get('page', '?')}페이지] {review['text'][:60]}...")
            
            print(f"Dentiste Board: 총 {len(unique_reviews)}개 고유 리뷰 수집 완료")
            return unique_reviews
            
        except Exception as e:
            print(f"Dentiste Board crawling error: {e}")
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
        return reviews
    
    def _extract_board_review_text(self, item_text):
        """게시판 리뷰에서 텍스트 추출 (더보기 확장 후)"""
        extracted = []
        
        # 패턴 1: 별점 다음의 리뷰 텍스트 (더보기 클릭 후 확장된 내용)
        pattern1 = r'[1-5]\.0.*?추천\d+\s*([가-힣\s\.\?!:😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉🌈🍀]{10,500}?)(?=더보기|조회|\d{2}\.\d{2}\.\d{2}|$)'
        matches1 = re.findall(pattern1, item_text, re.DOTALL)
        extracted.extend(matches1)
        
        # 패턴 2: 날짜 앞의 리뷰 텍스트
        pattern2 = r'([가-힣\s\.\?!:😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉🌈🍀]{15,500}?)\s*[가-힣]\*+\s*\d{2}\.\d{2}\.\d{2}'
        matches2 = re.findall(pattern2, item_text)
        extracted.extend(matches2)
        
        # 패턴 3: 감정 표현이 포함된 긴 텍스트 (확장된 리뷰)
        pattern3 = r'([가-힣\s\.\?!:😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉🌈🍀]{20,500}(?:좋아요|좋네요|만족|추천|감사|기분|잘.*산|너무.*좋|편해요|깔끔|청결|최고|사용|구매|배송|포장|제품|상품|비싸요|깨져|문제|불편|실망|별로|안.*좋)[가-힣\s\.\?!:😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉🌈🍀]{0,100})'
        matches3 = re.findall(pattern3, item_text)
        extracted.extend(matches3)
        
        # 패턴 4: 이모지가 포함된 리뷰 (확장 버전)
        pattern4 = r'([가-힣\s\.\?!:]{10,500}[😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉🌈🍀][가-힣\s\.\?!:😀😊👍❤️💕😄😍🥰😎🙂☺️✨💖🎉🌈🍀]*[가-힣\s\.\?!:]{0,50})'
        matches4 = re.findall(pattern4, item_text)
        extracted.extend(matches4)
        
        # 중복 제거 및 정리
        cleaned = []
        for text in extracted:
            text = re.sub(r'\s+', ' ', text.strip())  # 공백 정리
            # "더보기" 제거
            text = re.sub(r'더보기\s*>', '', text)
            
            if text and len(text) >= 10 and len(text) <= 1000:
                if re.search(r'[가-힣]{5,}', text):  # 최소 5글자 이상 한글 포함
                    # 너무 반복적인 패턴 제거
                    if not re.match(r'^(.+?)\1+$', text):  # 같은 문장 반복 제거
                        cleaned.append(text)
        
        return list(set(cleaned))
    
    def _is_valid_board_review(self, text):
        """게시판 리뷰가 유효한지 확인 (확장된 리뷰용)"""
        if not text or len(text) < 10 or len(text) > 1000:
            return False
        
        # 제외할 패턴들
        exclude_patterns = [
            r'베스트.*리뷰',
            r'조회\s*\d+$',
            r'^\d+$',
            r'^페이지',
            r'이전.*다음',
            r'검색.*조건',
            r'전체.*상품',
            r'카테고리',
            r'정렬.*순서'
        ]
        
        for pattern in exclude_patterns:
            if re.search(pattern, text):
                return False
        
        # 리뷰다운 패턴 확인
        review_indicators = [
            r'좋아요|좋네요|맛있|추천|만족|잘.*산|편해요|깔끔',  # 긍정적
            r'비싸요|깨져|문제|불편|실망|별로|안.*좋',  # 부정적
            r'사용|구매|배송|포장|제품|상품|리뷰',  # 일반적
            r'정말|너무|꽤|아주|매우|완전'  # 강조 표현
        ]
        
        has_review_indicator = any(re.search(pattern, text) for pattern in review_indicators)
        
        # 한글이 포함되어야 함
        if not re.search(r'[가-힣]{3,}', text):
            return False
        
        return has_review_indicator
    
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
        elif mall_type == 'dentiste':
            return self.crawl_dentiste(url)
        elif mall_type == 'dentiste_board':
            return self.crawl_dentiste_board(url)
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