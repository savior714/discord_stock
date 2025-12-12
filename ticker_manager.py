"""
티커 히스토리 관리 모듈
"""
import os
import json

TICKER_HISTORY_FILE = 'ticker_history.json'
MAX_HISTORY = 20  # 최대 저장 개수

def load_ticker_history():
    """티커 히스토리 불러오기"""
    if os.path.exists(TICKER_HISTORY_FILE):
        try:
            with open(TICKER_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_ticker_history(tickers):
    """티커 히스토리 저장"""
    try:
        # 중복 제거 및 최대 개수 제한
        unique_tickers = []
        for ticker in tickers:
            if ticker not in unique_tickers:
                unique_tickers.append(ticker)
        
        # 최대 개수 제한
        unique_tickers = unique_tickers[:MAX_HISTORY]
        
        with open(TICKER_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(unique_tickers, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"티커 히스토리 저장 오류: {e}")
        return False

def add_ticker_to_history(ticker):
    """티커를 히스토리에 추가"""
    history = load_ticker_history()
    
    # 이미 있으면 맨 앞으로 이동
    if ticker in history:
        history.remove(ticker)
    
    history.insert(0, ticker)
    save_ticker_history(history)
    return history

