import requests
import json

def test_single_analysis():
    url = "http://localhost:5000/analyze"
    
    test_texts = [
        "이 제품 정말 최고예요! 너무 만족합니다.",
        "완전 실망이네요. 돈 아깝습니다.",
        "배송도 빠르고 품질도 좋아요",
        "최악입니다. 다시는 구매하지 않을거예요.",
        "그냥 그래요. 보통입니다."
    ]
    
    print("=" * 50)
    print("단일 텍스트 분석 테스트")
    print("=" * 50)
    
    for text in test_texts:
        try:
            response = requests.post(url, json={"text": text})
            result = response.json()
            
            print(f"\n텍스트: {text}")
            print(f"결과: {result.get('label', 'N/A')}")
            print(f"신뢰도: {result.get('score', 0)}%")
            print("-" * 30)
        except Exception as e:
            print(f"오류 발생: {e}")

def test_batch_analysis():
    url = "http://localhost:5000/batch_analyze"
    
    texts = [
        "서비스가 정말 훌륭합니다",
        "품질이 너무 나빠요",
        "가격대비 괜찮은 것 같아요",
        "최악의 경험이었습니다",
        "다시 구매할 의향이 있어요",
        "환불 요청합니다",
        "추천하고 싶어요"
    ]
    
    print("\n" + "=" * 50)
    print("다중 텍스트 분석 테스트")
    print("=" * 50)
    
    try:
        response = requests.post(url, json={"texts": texts})
        result = response.json()
        
        print(f"\n전체 댓글 수: {result['summary']['total']}")
        print(f"부정 댓글 수: {result['summary']['negative']}")
        print(f"긍정 댓글 수: {result['summary']['positive']}")
        print(f"부정 댓글 비율: {result['summary']['negative_ratio']}%")
        
        print("\n상세 결과:")
        print("-" * 30)
        for r in result['results']:
            print(f"텍스트: {r['text']}")
            print(f"→ {r['label']} (신뢰도: {r['score']}%)")
            print()
            
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    print("API 테스트 시작...")
    print("(서버가 실행 중이어야 합니다)")
    
    try:
        test_single_analysis()
        test_batch_analysis()
    except requests.exceptions.ConnectionError:
        print("\n⚠️  서버에 연결할 수 없습니다.")
        print("먼저 'python app.py'로 서버를 실행해주세요.")
    
    print("\n테스트 완료!")