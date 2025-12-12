"""
실패한 티커들을 개별적으로 테스트하는 스크립트
"""
import yfinance as yf
import warnings
import time

warnings.filterwarnings('ignore')

# 실패한 티커 목록
failed_tickers = ['BRK.B', 'AGNS', 'COF', 'SWELL']

print("=" * 60)
print("실패한 티커 분석 시작")
print("=" * 60)
print()

for ticker in failed_tickers:
    print(f"\n{'='*60}")
    print(f"티커: {ticker}")
    print(f"{'='*60}")
    
    try:
        # 방법 1: Ticker.history() 사용
        print(f"[방법 1] Ticker.history() 테스트...")
        start = time.time()
        ticker_obj = yf.Ticker(ticker)
        df1 = ticker_obj.history(period='6mo', interval='1d', auto_adjust=True)
        elapsed1 = time.time() - start
        
        if df1.empty:
            print(f"  ❌ 결과: 빈 데이터프레임 (소요: {elapsed1:.2f}초)")
        else:
            print(f"  ✅ 결과: {len(df1)}개 행 (소요: {elapsed1:.2f}초)")
            print(f"  📅 날짜 범위: {df1.index[0]} ~ {df1.index[-1]}")
            print(f"  💰 최신 가격: {df1['Close'].iloc[-1]:.2f}")
        
        # 방법 2: yf.download() 사용
        print(f"\n[방법 2] yf.download() 테스트...")
        start = time.time()
        df2 = yf.download(ticker, period='6mo', interval='1d', progress=False, auto_adjust=True)
        elapsed2 = time.time() - start
        
        if df2.empty:
            print(f"  ❌ 결과: 빈 데이터프레임 (소요: {elapsed2:.2f}초)")
        else:
            print(f"  ✅ 결과: {len(df2)}개 행 (소요: {elapsed2:.2f}초)")
            print(f"  📅 날짜 범위: {df2.index[0]} ~ {df2.index[-1]}")
            if 'Close' in df2.columns:
                print(f"  💰 최신 가격: {df2['Close'].iloc[-1]:.2f}")
            elif isinstance(df2.columns, pd.MultiIndex):
                print(f"  💰 최신 가격: {df2[('Close', ticker)].iloc[-1]:.2f}")
        
        # 티커 정보 확인
        print(f"\n[정보] 티커 정보 확인...")
        info = ticker_obj.info
        if info:
            print(f"  회사명: {info.get('longName', 'N/A')}")
            print(f"  거래소: {info.get('exchange', 'N/A')}")
            print(f"  통화: {info.get('currency', 'N/A')}")
        
    except Exception as e:
        print(f"  ❌ 오류 발생: {type(e).__name__}")
        print(f"  📝 오류 메시지: {str(e)}")

print("\n" + "=" * 60)
print("분석 완료")
print("=" * 60)
