import discord
from discord.ext import tasks
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import io
import numpy as np
from datetime import datetime, time
import pytz
import os
from dotenv import load_dotenv
import logging
import threading
import asyncio
import queue
import json

# tkinter import (필수)
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
except ImportError as e:
    print(f"[ERROR] tkinter is not installed. Please install Python with tkinter support.")
    print(f"Error details: {e}")
    input("Press Enter to exit...")
    exit(1)
except Exception as e:
    print(f"[ERROR] tkinter initialization failed: {e}")
    print("\nThis is usually caused by missing Tcl/Tk libraries.")
    print("Please try one of the following solutions:")
    print("1. Reinstall Python and make sure to check 'tcl/tk and IDLE' option")
    print("2. Or install Python from python.org (includes tkinter by default)")
    print("3. Or use Python 3.11 or 3.12 instead of 3.13")
    input("\nPress Enter to exit...")
    exit(1)

# 환경 변수 로드
load_dotenv()

# ================= 설정값 =================
TOKEN = os.getenv('DISCORD_TOKEN', '')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID', '')
CHECK_SECONDS = 1800  # 30분 (1800초)
DISCORD_MESSAGE_INTERVAL = 10  # Discord 메시지 전송 간격 (초)
MAX_TICKERS = 500  # 최대 감시 가능 티커 수
# ==========================================

# 로깅 설정 (GUI용 핸들러 추가)
log_queue = queue.Queue()

class QueueHandler(logging.Handler):
    """로그를 큐에 추가하는 핸들러"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        QueueHandler(log_queue)
    ]
)

# Discord 라이브러리의 불필요한 경고 숨기기
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('discord.client').setLevel(logging.ERROR)
logging.getLogger('discord.gateway').setLevel(logging.ERROR)

plt.switch_backend('Agg')

# 전역 변수
TICKERS = []  # 감시할 티커 리스트
last_alert_dates = {}  # 각 티커별 마지막 알람 날짜
bot_running = False
bot_thread = None
loop = None
client = None
TICKER_HISTORY_FILE = 'ticker_history.json'
TICKER_SAVE_FILE = 'current_tickers.json'  # 현재 감시 중인 티커 저장 파일
ALERT_DATES_FILE = 'alert_dates.json'  # 알람 날짜 저장 파일
MAX_HISTORY = 20

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
        unique_tickers = []
        for ticker in tickers:
            if ticker not in unique_tickers:
                unique_tickers.append(ticker)
        unique_tickers = unique_tickers[:MAX_HISTORY]
        with open(TICKER_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(unique_tickers, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"티커 히스토리 저장 오류: {e}")
        return False

def load_current_tickers():
    """현재 감시 중인 티커 목록 불러오기"""
    if os.path.exists(TICKER_SAVE_FILE):
        try:
            with open(TICKER_SAVE_FILE, 'r', encoding='utf-8') as f:
                tickers = json.load(f)
                if isinstance(tickers, list):
                    logging.info(f"저장된 티커 불러오기: {len(tickers)}개")
                    return tickers
        except Exception as e:
            logging.error(f"티커 불러오기 오류: {e}")
    return []

def save_current_tickers():
    """현재 감시 중인 티커 목록 저장"""
    try:
        with open(TICKER_SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(TICKERS, f, ensure_ascii=False, indent=2)
        logging.info(f"티커 저장 완료: {len(TICKERS)}개")
        return True
    except Exception as e:
        logging.error(f"티커 저장 오류: {e}")
        return False

def load_alert_dates():
    """알람 날짜 정보 불러오기"""
    if os.path.exists(ALERT_DATES_FILE):
        try:
            with open(ALERT_DATES_FILE, 'r', encoding='utf-8') as f:
                dates = json.load(f)
                if isinstance(dates, dict):
                    logging.info(f"알람 날짜 정보 불러오기: {len(dates)}개 티커")
                    return dates
        except Exception as e:
            logging.error(f"알람 날짜 불러오기 오류: {e}")
    return {}

def save_alert_dates():
    """알람 날짜 정보 저장"""
    try:
        with open(ALERT_DATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(last_alert_dates, f, ensure_ascii=False, indent=2)
        logging.debug(f"알람 날짜 저장 완료: {len(last_alert_dates)}개")
        return True
    except Exception as e:
        logging.error(f"알람 날짜 저장 오류: {e}")
        return False

def add_tickers(new_tickers):
    """티커 리스트에 새로운 티커 추가"""
    global TICKERS
    
    added_count = 0
    skipped_count = 0
    
    for ticker in new_tickers:
        ticker = ticker.strip().upper()
        if ticker and ticker not in TICKERS:
            TICKERS.append(ticker)
            logging.info(f"✅ 티커 추가: {ticker}")
            added_count += 1
        elif ticker in TICKERS:
            logging.info(f"⚠️ 이미 등록된 티커 (건너뜀): {ticker}")
            skipped_count += 1
    
    # 히스토리에 저장
    history = load_ticker_history()
    for ticker in new_tickers:
        if ticker not in history:
            history.insert(0, ticker)
    save_ticker_history(history)
    
    # 현재 티커 목록 저장
    save_current_tickers()
    
    logging.info(f"📊 총 {added_count}개 티커 추가됨, {skipped_count}개 중복 건너뜀. 현재 감시 중인 티커: {len(TICKERS)}개")
    logging.info(f"📋 전체 티커 목록: {', '.join(TICKERS)}")

def is_active_time():
    """
    현재 시간이 한국 시간(KST) 기준 오전 10시 ~ 새벽 4시 사이인지 확인
    """
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst).time()
    
    start_time = time(10, 0, 0)  # 오전 10시
    end_time = time(4, 0, 0)     # 새벽 4시
    
    if now >= start_time or now < end_time:
        return True
    return False

def calculate_rsi_wilders(prices, period=14):
    """
    Wilder's smoothing을 사용한 정확한 RSI 계산
    """
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    
    for i in range(period, len(gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_mfi(df, period=14):
    """
    Money Flow Index (MFI) 계산
    """
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    raw_money_flow = tp * df['Volume']
    
    pos_flow = raw_money_flow.where(tp > tp.shift(1), 0)
    neg_flow = raw_money_flow.where(tp < tp.shift(1), 0)
    
    pos_mf = pos_flow.rolling(period).sum()
    neg_mf = neg_flow.rolling(period).sum()
    
    mfi_ratio = pos_mf / neg_mf
    mfi_ratio = mfi_ratio.replace([np.inf, -np.inf], np.nan)
    mfi = 100 - (100 / (1 + mfi_ratio))
    
    return mfi

def get_data_and_indicators(ticker):
    """
    일봉 데이터와 보조지표 계산
    """
    try:
        # FutureWarning 억제
        import warnings
        warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
        
        df = yf.download(ticker, period='6mo', interval='1d', progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 20:
            logging.warning(f"데이터 부족: {len(df)}개 행만 수신됨")
            return None
        
        # MultiIndex 컬럼을 단순 컬럼으로 변환 (yfinance 최신 버전 대응)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.sort_index()
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        
        if len(df) < 20:
            logging.warning("NaN 제거 후 데이터 부족")
            return None
        
        df['RSI'] = calculate_rsi_wilders(df['Close'], period=14)
        df['MFI'] = calculate_mfi(df, period=14)
        
        ma20 = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        df['BB_Lower'] = ma20 - (std * 1)
        df['BB_Upper'] = ma20 + (std * 1)
        df['BB_Middle'] = ma20
        
        latest = df.iloc[-1]
        if pd.isna(latest['RSI']) or pd.isna(latest['MFI']) or pd.isna(latest['BB_Lower']):
            logging.warning("최신 데이터에 NaN 값 존재")
            return None
        
        return df
        
    except Exception as e:
        logging.error(f"데이터 수신 오류: {e}")
        return None

def check_bollinger_touch(df):
    """
    볼린저 밴드 하단 터치 확인
    """
    if len(df) < 2:
        return False
    
    current = df.iloc[-1]
    current_touch = current['Close'] <= current['BB_Lower']
    close_to_lower = abs(current['Close'] - current['BB_Lower']) / current['BB_Lower'] < 0.001
    
    return current_touch or close_to_lower

def draw_chart(df, ticker):
    """
    차트 생성 (최근 60일)
    """
    try:
        df_plot = df.tail(60).copy()
        
        plt.style.use('dark_background')
        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, 
            figsize=(12, 10), 
            gridspec_kw={'height_ratios': [2, 1, 1]}
        )
        
        ax1.plot(df_plot.index, df_plot['Close'], color='white', linewidth=2, label='Price')
        ax1.plot(df_plot.index, df_plot['BB_Middle'], color='blue', linestyle='--', alpha=0.7, label='BB Middle (MA20)')
        ax1.plot(df_plot.index, df_plot['BB_Lower'], color='red', linestyle='--', linewidth=1.5, label='BB Lower (1std)')
        ax1.plot(df_plot.index, df_plot['BB_Upper'], color='green', linestyle='--', alpha=0.7, label='BB Upper (1std)')
        ax1.fill_between(df_plot.index, df_plot['BB_Upper'], df_plot['BB_Lower'], color='gray', alpha=0.1)
        ax1.set_title(f'{ticker} Daily Chart (Last 60 Days)', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylabel('Price', fontsize=10)
        
        latest_price = df_plot['Close'].iloc[-1]
        latest_date = df_plot.index[-1]
        ax1.scatter([latest_date], [latest_price], color='yellow', s=100, zorder=5)
        ax1.annotate(f'{latest_price:.2f}', 
                    xy=(latest_date, latest_price),
                    xytext=(10, 10), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                    fontsize=9)
        
        ax2.plot(df_plot.index, df_plot['RSI'], color='cyan', linewidth=2, label='RSI(14)')
        ax2.axhline(35, color='red', linestyle='--', linewidth=1.5, label='Threshold (35)')
        ax2.axhline(70, color='orange', linestyle=':', alpha=0.5)
        ax2.axhline(30, color='green', linestyle=':', alpha=0.5)
        ax2.fill_between(df_plot.index, 0, 35, color='red', alpha=0.1)
        ax2.set_ylabel('RSI', fontsize=10)
        ax2.set_ylim(0, 100)
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        latest_rsi = df_plot['RSI'].iloc[-1]
        ax2.scatter([latest_date], [latest_rsi], color='cyan', s=50, zorder=5)
        
        ax3.plot(df_plot.index, df_plot['MFI'], color='yellow', linewidth=2, label='MFI(14)')
        ax3.axhline(35, color='red', linestyle='--', linewidth=1.5, label='Threshold (35)')
        ax3.axhline(80, color='orange', linestyle=':', alpha=0.5)
        ax3.axhline(20, color='green', linestyle=':', alpha=0.5)
        ax3.fill_between(df_plot.index, 0, 35, color='red', alpha=0.1)
        ax3.set_ylabel('MFI', fontsize=10)
        ax3.set_ylim(0, 100)
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        ax3.set_xlabel('Date', fontsize=10)
        
        latest_mfi = df_plot['MFI'].iloc[-1]
        ax3.scatter([latest_date], [latest_mfi], color='yellow', s=50, zorder=5)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf
        
    except Exception as e:
        logging.error(f"차트 생성 오류: {e}")
        return None

@tasks.loop(seconds=CHECK_SECONDS)
async def check_price():
    """
    주기적으로 주가와 보조지표를 확인하고 조건 만족 시 알람 전송 (대규모 다중 티커 지원)
    """
    global last_alert_dates, TICKERS
    
    if not is_active_time():
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%H:%M:%S")
        logging.debug(f"[{now_kst}] 감시 시간이 아닙니다. (10:00 ~ 04:00 KST)")
        return

    channel = client.get_channel(int(CHANNEL_ID))
    if not channel:
        logging.error(f"채널을 찾을 수 없습니다: {CHANNEL_ID}")
        return

    logging.info(f"=== 감시 시작: {len(TICKERS)}개 티커 체크 ===")
    
    # 알림 전송 카운터
    alert_count = 0
    
    # 각 티커에 대해 체크하고 즉시 알림 전송
    for idx, ticker in enumerate(TICKERS, 1):
        try:
            df = get_data_and_indicators(ticker)
            if df is None:
                logging.warning(f"{ticker}: 데이터를 가져올 수 없습니다.")
                continue

            today = df.iloc[-1]
            current_date = df.index[-1]
            current_date_str = current_date.strftime('%Y-%m-%d') if hasattr(current_date, 'strftime') else str(current_date)[:10]
            
            cond_mfi = today['MFI'] < 35
            cond_rsi = today['RSI'] < 35
            cond_bb = check_bollinger_touch(df)
            
            all_conditions_met = cond_mfi and cond_rsi and cond_bb
            
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
            
            status_icon = "✅" if all_conditions_met else "❌"
            logging.info(
                f"[{now_kst}] {status_icon} {ticker} | "
                f"Date: {current_date_str} | "
                f"Price: {today['Close']:.2f} | "
                f"RSI: {today['RSI']:.2f} {'✓' if cond_rsi else '✗'} | "
                f"MFI: {today['MFI']:.2f} {'✓' if cond_mfi else '✗'} | "
                f"BB: {'✓' if cond_bb else '✗'} "
                f"(Lower: {today['BB_Lower']:.2f})"
            )
            
            if all_conditions_met:
                # 티커별로 마지막 알람 날짜 확인
                last_alert = last_alert_dates.get(ticker)
                logging.info(f"🔍 {ticker} 알람 체크: 마지막 알람={last_alert}, 현재 날짜={current_date_str}")
                
                if last_alert != current_date_str:
                    # 즉시 알림 전송
                    try:
                        alert_count += 1
                        logging.info(f"📤 {ticker}: 알림 전송 시작 ({alert_count}번째)")
                        
                        msg = (
                            f"🚨 **{ticker} 매수 조건 포착!** ({now_kst})\n\n"
                            f"**조건 확인:**\n"
                            f"✅ RSI(14): `{today['RSI']:.2f}` (< 35)\n"
                            f"✅ MFI(14): `{today['MFI']:.2f}` (< 35)\n"
                            f"✅ 볼린저 밴드: 하단 터치\n"
                            f"   - 현재가: `{today['Close']:.2f}`\n"
                            f"   - 하단 밴드: `{today['BB_Lower']:.2f}`\n\n"
                            f"📊 차트를 확인하세요!"
                        )
                        
                        chart_buf = draw_chart(df, ticker)
                        if chart_buf:
                            file = discord.File(chart_buf, filename=f'{ticker}_chart.png')
                            await channel.send(content=msg, file=file)
                        else:
                            await channel.send(content=msg)
                        
                        last_alert_dates[ticker] = current_date_str
                        logging.info(f"✅ {ticker}: 알림 전송 완료 ({alert_count}번째)")
                        
                        # Discord 메시지 전송 간격 제한 (10초) - 다음 티커 체크 전 대기
                        if alert_count > 0 and idx < len(TICKERS):
                            logging.info(f"⏱️ Discord 메시지 간격 유지: {DISCORD_MESSAGE_INTERVAL}초 대기")
                            await asyncio.sleep(DISCORD_MESSAGE_INTERVAL)
                            
                    except Exception as e:
                        logging.error(f"{ticker} 알림 전송 오류: {e}", exc_info=True)
                else:
                    logging.info(f"⏭️ {ticker}: 조건 만족했으나 이미 오늘({current_date_str}) 알람 전송됨 - 건너뜀")

        except Exception as e:
            logging.error(f"{ticker} 체크 중 오류 발생: {e}", exc_info=True)
        
        # 진행 상황 로그 (100개마다)
        if idx % 100 == 0:
            logging.info(f"진행 중... {idx}/{len(TICKERS)} 완료, 알림 전송: {alert_count}개")
    
    # 알람 날짜 정보 저장
    if alert_count > 0:
        save_alert_dates()
        logging.info(f"=== 알림 전송 완료: 총 {alert_count}개 전송됨 ===")
    else:
        logging.info("=== 조건 만족 종목 없음 ===")
    
    logging.info(f"=== 감시 완료: {len(TICKERS)}개 티커 체크 완료 ===")

# on_ready는 run_bot 함수 내부에서 정의됨

def run_bot():
    """
    Discord 봇을 실행하는 함수 (별도 스레드에서 실행)
    """
    global loop, TICKERS, bot_running, client
    
    try:
        # 새로운 Discord client 생성 (음성 기능 비활성화)
        intents = discord.Intents.default()
        intents.voice_states = False  # 음성 상태 비활성화
        client = discord.Client(intents=intents)
        
        # on_ready 이벤트 핸들러 등록
        @client.event
        async def on_ready():
            logging.info(f'디스코드 봇 로그인 완료: {client.user}')
            ticker_preview = ', '.join(TICKERS[:10]) + ("..." if len(TICKERS) > 10 else "")
            logging.info(f'감시 종목: {ticker_preview} ({len(TICKERS)}개)')
            logging.info(f'체크 주기: {CHECK_SECONDS}초 (30분)')
            logging.info(f'Discord 메시지 간격: {DISCORD_MESSAGE_INTERVAL}초')
            logging.info(f'최대 감시 가능: {MAX_TICKERS}개')
            logging.info(f'감시 시간: 오전 10시 ~ 새벽 4시 (KST)')
            
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f'현재 시간 (KST): {now_kst}')
            
            if is_active_time():
                logging.info("✅ 감시 시간입니다. 체크를 시작합니다.")
            else:
                logging.info("⏸ 감시 시간이 아닙니다. 대기 중...")
            
            # Task가 이미 실행 중이 아닐 때만 시작
            if not check_price.is_running():
                check_price.start()
                logging.info("📊 체크 루프 시작됨")
            else:
                logging.info("⚠️ 체크 루프가 이미 실행 중입니다.")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(client.start(TOKEN))
    except Exception as e:
        logging.error(f"봇 실행 오류: {e}", exc_info=True)
    finally:
        if loop and not loop.is_closed():
            try:
                if client:
                    loop.run_until_complete(client.close())
            except:
                pass
            loop.close()

class StockBotGUI:
    def __init__(self, root):
        global TICKERS, last_alert_dates
        
        self.root = root
        self.root.title("Discord 주가 알람 봇 - 다중 티커 감시")
        self.root.geometry("900x750")
        self.root.resizable(True, True)
        
        # 스타일 설정
        style = ttk.Style()
        style.theme_use('clam')
        
        # 저장된 티커 불러오기
        saved_tickers = load_current_tickers()
        if saved_tickers:
            # 중복 제거 (순서 유지)
            seen = set()
            unique_tickers = []
            duplicates = []
            for ticker in saved_tickers:
                if ticker not in seen:
                    seen.add(ticker)
                    unique_tickers.append(ticker)
                else:
                    duplicates.append(ticker)
            
            TICKERS = unique_tickers
            logging.info(f"💾 이전 세션의 티커 복원: {len(TICKERS)}개")
            
            if duplicates:
                logging.info(f"🔧 중복 티커 제거됨: {', '.join(duplicates)}")
                save_current_tickers()  # 중복 제거된 목록 저장
        
        # 저장된 알람 날짜 불러오기
        saved_alert_dates = load_alert_dates()
        if saved_alert_dates:
            last_alert_dates.update(saved_alert_dates)
            logging.info(f"📅 알람 날짜 정보 복원: {len(saved_alert_dates)}개")
            # 복원된 알람 날짜 상세 로그
            for ticker, date in saved_alert_dates.items():
                logging.info(f"   - {ticker}: {date}")
        
        # 티커 히스토리 로드
        self.ticker_history = load_ticker_history()
        
        self.setup_ui()
        self.process_log_queue()
        
    def setup_ui(self):
        """UI 구성"""
        # 상단 프레임 - 티커 입력 및 제어
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        # 티커 입력
        ttk.Label(top_frame, text="종목 티커 추가 (쉼표로 구분):", font=('맑은 고딕', 10)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.ticker_entry = ttk.Entry(top_frame, width=40, font=('맑은 고딕', 10))
        self.ticker_entry.grid(row=0, column=1, padx=5, pady=5)
        # 빈 상태로 시작
        
        # 티커 추가 버튼
        self.add_ticker_button = ttk.Button(top_frame, text="티커 추가", command=self.add_tickers_only, width=12)
        self.add_ticker_button.grid(row=0, column=2, padx=5, pady=5)
        
        self.ticker_count_label = ttk.Label(top_frame, text=f"현재: {len(TICKERS)}/{MAX_TICKERS}개", 
                 font=('맑은 고딕', 9), foreground='gray')
        self.ticker_count_label.grid(row=0, column=3, padx=5, sticky=tk.W)
        
        # 버튼 프레임
        button_frame = ttk.Frame(top_frame)
        button_frame.grid(row=1, column=0, columnspan=4, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="봇 시작", command=self.start_bot, width=15)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="봇 중지", command=self.stop_bot, width=15, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(button_frame, text="티커 전체 삭제", command=self.clear_all_tickers, width=15)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        # 상태 표시
        status_frame = ttk.LabelFrame(self.root, text="상태", padding="10")
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="대기 중...", font=('맑은 고딕', 10))
        self.status_label.pack(anchor=tk.W)
        
        # 등록된 티커 목록 표시 (테이블)
        ticker_list_frame = ttk.LabelFrame(self.root, text="등록된 티커 목록", padding="10")
        ticker_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 스크롤바가 있는 프레임
        ticker_scroll_frame = ttk.Frame(ticker_list_frame)
        ticker_scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        # 스크롤바
        ticker_scrollbar = ttk.Scrollbar(ticker_scroll_frame)
        ticker_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Treeview (테이블)
        columns = ('번호', '티커', '마지막 알람')
        self.ticker_tree = ttk.Treeview(ticker_scroll_frame, columns=columns, show='headings', 
                                        height=8, yscrollcommand=ticker_scrollbar.set)
        
        # 컬럼 설정
        self.ticker_tree.heading('번호', text='번호')
        self.ticker_tree.heading('티커', text='티커')
        self.ticker_tree.heading('마지막 알람', text='마지막 알람 날짜')
        
        self.ticker_tree.column('번호', width=50, anchor='center')
        self.ticker_tree.column('티커', width=100, anchor='center')
        self.ticker_tree.column('마지막 알람', width=150, anchor='center')
        
        self.ticker_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ticker_scrollbar.config(command=self.ticker_tree.yview)
        
        # 티커 목록 버튼 프레임
        ticker_button_frame = ttk.Frame(ticker_list_frame)
        ticker_button_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(ticker_button_frame, text="선택한 티커 삭제", 
                  command=self.delete_selected_ticker, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(ticker_button_frame, text="목록 새로고침", 
                  command=self.refresh_ticker_list, width=20).pack(side=tk.LEFT, padx=5)
        
        # 초기 티커 목록 표시
        self.refresh_ticker_list()
        
        # 로그 영역
        log_frame = ttk.LabelFrame(self.root, text="로그", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, font=('Consolas', 9), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # 초기 로그
        self.add_log("=" * 60)
        self.add_log("Discord 주가 알람 봇이 시작되었습니다.")
        self.add_log("=" * 60)
        self.add_log("")
        
        if TICKERS:
            ticker_preview = ', '.join(TICKERS[:10]) + ("..." if len(TICKERS) > 10 else "")
            self.add_log(f"💾 이전 세션 복원: {len(TICKERS)}개 티커")
            self.add_log(f"   → {ticker_preview}")
            self.add_log("")
            self.add_log("'봇 시작' 버튼을 클릭하여 감시를 시작하세요.")
        else:
            self.add_log("사용 방법:")
            self.add_log("1. 종목 티커를 입력하세요 (예: AAPL, TSLA, 005930.KS)")
            self.add_log("2. '티커 추가' 버튼을 클릭하세요")
            self.add_log("3. '봇 시작' 버튼을 클릭하여 감시를 시작하세요")
        
        self.add_log("")
        
    def add_log(self, message):
        """로그 추가"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def process_log_queue(self):
        """로그 큐에서 메시지를 가져와 표시"""
        try:
            while True:
                message = log_queue.get_nowait()
                self.add_log(message)
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_log_queue)
    
    def refresh_ticker_list(self):
        """티커 목록 테이블 새로고침"""
        # 기존 항목 삭제
        for item in self.ticker_tree.get_children():
            self.ticker_tree.delete(item)
        
        # 티커 목록 추가
        for idx, ticker in enumerate(TICKERS, 1):
            last_alert = last_alert_dates.get(ticker, '없음')
            self.ticker_tree.insert('', tk.END, values=(idx, ticker, last_alert))
    
    def delete_selected_ticker(self):
        """선택한 티커 삭제"""
        global TICKERS, last_alert_dates
        
        selected_items = self.ticker_tree.selection()
        if not selected_items:
            messagebox.showwarning("선택 필요", "삭제할 티커를 선택해주세요!")
            return
        
        if bot_running:
            messagebox.showwarning("경고", "봇 실행 중에는 티커를 삭제할 수 없습니다.\n먼저 봇을 중지해주세요.")
            return
        
        # 선택된 티커 정보 가져오기
        tickers_to_delete = []
        for item in selected_items:
            values = self.ticker_tree.item(item)['values']
            ticker = values[1]  # 티커는 두 번째 컬럼
            tickers_to_delete.append(ticker)
        
        # 확인 메시지
        ticker_list = ', '.join(tickers_to_delete)
        result = messagebox.askyesno("확인", 
            f"다음 티커를 삭제하시겠습니까?\n\n{ticker_list}\n\n"
            f"({len(tickers_to_delete)}개 선택됨)")
        
        if result:
            # 티커 삭제
            for ticker in tickers_to_delete:
                if ticker in TICKERS:
                    TICKERS.remove(ticker)
                    logging.info(f"🗑️ 티커 삭제: {ticker}")
                
                # 알람 날짜 정보도 삭제
                if ticker in last_alert_dates:
                    del last_alert_dates[ticker]
            
            # 저장
            save_current_tickers()
            save_alert_dates()
            
            # UI 업데이트
            self.refresh_ticker_list()
            self.ticker_count_label.config(text=f"현재: {len(TICKERS)}/{MAX_TICKERS}개")
            
            self.add_log(f"[삭제] {len(tickers_to_delete)}개 티커 삭제 완료: {ticker_list}")
            self.add_log(f"[현황] 남은 감시 종목: {len(TICKERS)}개")
            
            messagebox.showinfo("삭제 완료", 
                f"{len(tickers_to_delete)}개 티커가 삭제되었습니다.\n남은 티커: {len(TICKERS)}개")
        
    def add_tickers_only(self):
        """티커만 추가 (봇 실행 중에도 가능)"""
        global TICKERS
        
        # 티커 확인
        ticker_input = self.ticker_entry.get().strip().upper()
        if not ticker_input:
            messagebox.showwarning("입력 필요", "추가할 종목 티커를 입력해주세요!")
            return
        
        # 쉼표로 구분된 티커들을 파싱
        new_tickers = [t.strip() for t in ticker_input.split(',') if t.strip()]
        
        if not new_tickers:
            messagebox.showerror("오류", "유효한 티커를 입력해주세요!")
            return
        
        # 최대 티커 수 체크
        if len(TICKERS) + len(new_tickers) > MAX_TICKERS:
            messagebox.showerror("제한 초과", 
                f"최대 {MAX_TICKERS}개까지만 감시할 수 있습니다.\n현재 등록된 티커: {len(TICKERS)}개")
            return
        
        # 티커 추가
        add_tickers(new_tickers)
        
        # UI 업데이트
        self.ticker_count_label.config(text=f"현재: {len(TICKERS)}/{MAX_TICKERS}개")
        self.refresh_ticker_list()
        
        # 입력 필드 초기화
        self.ticker_entry.delete(0, tk.END)
        
        if bot_running:
            self.add_log(f"[추가] 티커 추가 완료 (봇 실행 중): {', '.join(new_tickers)}")
            self.add_log(f"[안내] 다음 체크 주기부터 새 티커가 감시됩니다.")
            self.add_log(f"[안내] 조건 만족 시 즉시 알람이 전송됩니다.")
        else:
            self.add_log(f"[추가] 티커 추가 완료: {', '.join(new_tickers)}")
        
        self.add_log(f"[현황] 전체 감시 종목: {len(TICKERS)}개")
        
        if bot_running:
            messagebox.showinfo("추가 완료", 
                f"{len(new_tickers)}개 티커가 추가되었습니다.\n"
                f"현재 총 {len(TICKERS)}개 감시 중\n\n"
                f"※ 다음 체크 주기부터 감시됩니다.\n"
                f"※ 조건 만족 시 즉시 알람이 전송됩니다.")
        else:
            messagebox.showinfo("추가 완료", f"{len(new_tickers)}개 티커가 추가되었습니다.\n현재 총 {len(TICKERS)}개 감시 중")
    
    def clear_all_tickers(self):
        """전체 티커 삭제"""
        global TICKERS
        
        if not TICKERS:
            messagebox.showinfo("알림", "삭제할 티커가 없습니다.")
            return
        
        if bot_running:
            messagebox.showwarning("경고", "봇 실행 중에는 티커를 삭제할 수 없습니다.\n먼저 봇을 중지해주세요.")
            return
        
        result = messagebox.askyesno("확인", f"현재 등록된 {len(TICKERS)}개의 티커를 모두 삭제하시겠습니까?")
        if result:
            TICKERS.clear()
            last_alert_dates.clear()
            save_current_tickers()  # 빈 상태 저장
            save_alert_dates()
            self.ticker_count_label.config(text=f"현재: 0/{MAX_TICKERS}개")
            self.refresh_ticker_list()
            self.add_log(f"[삭제] 모든 티커가 삭제되었습니다.")
            messagebox.showinfo("삭제 완료", "모든 티커가 삭제되었습니다.")
    
    def start_bot(self):
        """봇 시작"""
        global TICKERS, bot_running, bot_thread, last_alert_dates
        
        # 티커 확인
        if not TICKERS:
            messagebox.showerror("오류", "감시할 티커가 없습니다!\n먼저 '티커 추가' 버튼으로 티커를 추가해주세요.")
            return
        
        # 설정 확인
        if not TOKEN or TOKEN == '여기에_디스코드_봇_토큰':
            messagebox.showerror("오류", ".env 파일에 DISCORD_TOKEN을 설정해주세요!")
            return
        
        if not CHANNEL_ID or CHANNEL_ID == '123456789012345678':
            messagebox.showerror("오류", ".env 파일에 DISCORD_CHANNEL_ID를 설정해주세요!")
            return
        
        if bot_running:
            messagebox.showwarning("경고", "봇이 이미 실행 중입니다!")
            return
        
        bot_running = True
        
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        # 티커 추가는 봇 실행 중에도 가능하도록 활성화 유지
        # self.ticker_entry.config(state=tk.DISABLED)
        # self.add_ticker_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        self.status_label.config(text="🟢 실행 중...")
        
        # 티커 미리보기 생성
        ticker_preview = ', '.join(TICKERS[:10]) + ("..." if len(TICKERS) > 10 else "")
        
        self.add_log("")
        self.add_log(f"[시작] 봇을 시작합니다...")
        self.add_log(f"[설정] 전체 감시 종목: {ticker_preview} (총 {len(TICKERS)}개)")
        if len(TICKERS) > 10:
            self.add_log(f"[상세] 전체 티커 목록: {', '.join(TICKERS)}")
        self.add_log(f"[설정] 체크 주기: {CHECK_SECONDS}초 (30분)")
        self.add_log(f"[설정] Discord 메시지 간격: {DISCORD_MESSAGE_INTERVAL}초")
        self.add_log(f"[설정] 감시 시간: 오전 10시 ~ 새벽 4시 (KST)")
        self.add_log("")
        
        # 별도 스레드에서 봇 실행
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        
    def stop_bot(self):
        """봇 중지"""
        global bot_running, loop
        
        if not bot_running:
            return
        
        bot_running = False
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        # 티커 추가는 항상 활성화되어 있으므로 상태 변경 불필요
        # self.ticker_entry.config(state=tk.NORMAL)
        # self.add_ticker_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        self.status_label.config(text="🔴 중지됨")
        
        self.add_log("")
        self.add_log("[중지] 봇을 중지합니다...")
        
        # 봇 종료
        try:
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(client.close(), loop)
            check_price.cancel()
        except Exception as e:
            logging.error(f"봇 중지 오류: {e}")
        
        self.add_log("[안내] 봇을 다시 시작하려면 프로그램을 재시작하세요.")

if __name__ == '__main__':
    try:
        root = tk.Tk()
        app = StockBotGUI(root)
        root.mainloop()
    except tk.TclError as e:
        error_msg = str(e)
        print("=" * 60)
        print("[ERROR] tkinter GUI initialization failed!")
        print("=" * 60)
        print(f"\nError: {error_msg}")
        print("\nThis error usually means Tcl/Tk libraries are missing.")
        print("\nSolutions:")
        print("1. Reinstall Python from python.org")
        print("   - Make sure to check 'tcl/tk and IDLE' during installation")
        print("   - Or use the full installer which includes tkinter by default")
        print("\n2. If using Python 3.13, try Python 3.11 or 3.12 instead")
        print("   (Python 3.13 sometimes has tkinter issues on Windows)")
        print("\n3. Install Tcl/Tk manually:")
        print("   - Download ActiveTcl from: https://www.activestate.com/products/tcl/")
        print("   - Or use: winget install ActiveState.ActiveTcl")
        print("\n4. Alternative: Use a virtual environment with Python 3.11/3.12")
        print("=" * 60)
        input("\nPress Enter to exit...")
        exit(1)
    except Exception as e:
        logging.error(f"GUI error: {e}", exc_info=True)
        print(f"\n[ERROR] Failed to start GUI: {e}")
        input("Press Enter to exit...")
        exit(1)

