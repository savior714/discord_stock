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
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import asyncio
import queue

# 환경 변수 로드
load_dotenv()

# ================= 설정값 =================
TOKEN = os.getenv('DISCORD_TOKEN', '')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID', '')
CHECK_SECONDS = 600  # 10분 (600초)
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

plt.switch_backend('Agg')
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# 전역 변수
TICKER = ''
last_alert_date = None
bot_running = False
bot_thread = None
loop = None

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
        df = yf.download(ticker, period='6mo', interval='1d', progress=False)
        
        if df.empty or len(df) < 20:
            logging.warning(f"데이터 부족: {len(df)}개 행만 수신됨")
            return None
        
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
    주기적으로 주가와 보조지표를 확인하고 조건 만족 시 알람 전송
    """
    global last_alert_date, TICKER
    
    if not is_active_time():
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%H:%M:%S")
        logging.debug(f"[{now_kst}] 감시 시간이 아닙니다. (10:00 ~ 04:00 KST)")
        return

    channel = client.get_channel(int(CHANNEL_ID))
    if not channel:
        logging.error(f"채널을 찾을 수 없습니다: {CHANNEL_ID}")
        return

    try:
        df = get_data_and_indicators(TICKER)
        if df is None:
            logging.warning("데이터를 가져올 수 없습니다.")
            return

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
            f"[{now_kst}] {status_icon} {TICKER} | "
            f"Date: {current_date_str} | "
            f"Price: {today['Close']:.2f} | "
            f"RSI: {today['RSI']:.2f} {'✓' if cond_rsi else '✗'} | "
            f"MFI: {today['MFI']:.2f} {'✓' if cond_mfi else '✗'} | "
            f"BB: {'✓' if cond_bb else '✗'} "
            f"(Lower: {today['BB_Lower']:.2f})"
        )
        
        if all_conditions_met:
            if last_alert_date != current_date_str:
                msg = (
                    f"🚨 **{TICKER} 매수 조건 포착!** ({now_kst})\n\n"
                    f"**조건 확인:**\n"
                    f"✅ RSI(14): `{today['RSI']:.2f}` (< 35)\n"
                    f"✅ MFI(14): `{today['MFI']:.2f}` (< 35)\n"
                    f"✅ 볼린저 밴드: 하단 터치\n"
                    f"   - 현재가: `{today['Close']:.2f}`\n"
                    f"   - 하단 밴드: `{today['BB_Lower']:.2f}`\n\n"
                    f"📊 차트를 확인하세요!"
                )
                
                chart_buf = draw_chart(df, TICKER)
                if chart_buf:
                    file = discord.File(chart_buf, filename=f'{TICKER}_chart.png')
                    await channel.send(content=msg, file=file)
                    logging.info(f">>> 알림 전송 완료: {TICKER} (날짜: {current_date_str})")
                else:
                    await channel.send(content=msg)
                    logging.warning("차트 생성 실패, 텍스트만 전송")
                
                last_alert_date = current_date_str
            else:
                logging.debug(f"조건 만족했으나 이미 오늘({current_date_str}) 알람 전송됨 (중복 방지)")

    except Exception as e:
        logging.error(f"체크 중 오류 발생: {e}", exc_info=True)

@client.event
async def on_ready():
    """
    봇이 준비되었을 때 실행
    """
    logging.info(f'디스코드 봇 로그인 완료: {client.user}')
    logging.info(f'감시 종목: {TICKER}')
    logging.info(f'체크 주기: {CHECK_SECONDS}초 (10분)')
    logging.info(f'감시 시간: 오전 10시 ~ 새벽 4시 (KST)')
    
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f'현재 시간 (KST): {now_kst}')
    
    if is_active_time():
        logging.info("✅ 감시 시간입니다. 체크를 시작합니다.")
    else:
        logging.info("⏸ 감시 시간이 아닙니다. 대기 중...")
    
    check_price.start()

def run_bot():
    """
    Discord 봇을 실행하는 함수 (별도 스레드에서 실행)
    """
    global loop, TICKER, bot_running
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(client.start(TOKEN))
    except Exception as e:
        logging.error(f"봇 실행 오류: {e}", exc_info=True)
    finally:
        loop.close()

class StockBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord 주가 알람 봇")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        # 스타일 설정
        style = ttk.Style()
        style.theme_use('clam')
        
        self.setup_ui()
        self.process_log_queue()
        
    def setup_ui(self):
        """UI 구성"""
        # 상단 프레임 - 티커 입력 및 제어
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        # 티커 입력
        ttk.Label(top_frame, text="종목 티커:", font=('맑은 고딕', 10)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.ticker_entry = ttk.Entry(top_frame, width=20, font=('맑은 고딕', 10))
        self.ticker_entry.grid(row=0, column=1, padx=5, pady=5)
        self.ticker_entry.insert(0, os.getenv('TICKER', 'AAPL'))
        ttk.Label(top_frame, text="(예: AAPL, TSLA, 005930.KS)", font=('맑은 고딕', 9), foreground='gray').grid(row=0, column=2, padx=5, sticky=tk.W)
        
        # 버튼 프레임
        button_frame = ttk.Frame(top_frame)
        button_frame.grid(row=1, column=0, columnspan=3, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="봇 시작", command=self.start_bot, width=15)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="봇 중지", command=self.stop_bot, width=15, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # 상태 표시
        status_frame = ttk.LabelFrame(self.root, text="상태", padding="10")
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="대기 중...", font=('맑은 고딕', 10))
        self.status_label.pack(anchor=tk.W)
        
        self.ticker_label = ttk.Label(status_frame, text="감시 종목: 없음", font=('맑은 고딕', 9), foreground='gray')
        self.ticker_label.pack(anchor=tk.W)
        
        # 설정 확인
        config_frame = ttk.LabelFrame(self.root, text="설정 확인", padding="10")
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        token_status = "✅ 설정됨" if TOKEN and TOKEN != '여기에_디스코드_봇_토큰' else "❌ 미설정"
        channel_status = "✅ 설정됨" if CHANNEL_ID and CHANNEL_ID != '123456789012345678' else "❌ 미설정"
        
        ttk.Label(config_frame, text=f"Discord 토큰: {token_status}", font=('맑은 고딕', 9)).pack(anchor=tk.W)
        ttk.Label(config_frame, text=f"채널 ID: {channel_status}", font=('맑은 고딕', 9)).pack(anchor=tk.W)
        
        if token_status == "❌ 미설정" or channel_status == "❌ 미설정":
            ttk.Label(config_frame, text="⚠️ .env 파일을 확인하세요!", font=('맑은 고딕', 9), foreground='red').pack(anchor=tk.W, pady=5)
        
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
        self.add_log("사용 방법:")
        self.add_log("1. 종목 티커를 입력하세요 (예: AAPL, TSLA, 005930.KS)")
        self.add_log("2. '봇 시작' 버튼을 클릭하세요")
        self.add_log("3. 로그를 확인하여 봇 상태를 모니터링하세요")
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
        
    def start_bot(self):
        """봇 시작"""
        global TICKER, bot_running, bot_thread, last_alert_date
        
        # 티커 확인
        ticker = self.ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showerror("오류", "종목 티커를 입력해주세요!")
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
        
        TICKER = ticker
        last_alert_date = None
        bot_running = True
        
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.ticker_entry.config(state=tk.DISABLED)
        self.status_label.config(text="🟢 실행 중...")
        self.ticker_label.config(text=f"감시 종목: {TICKER}")
        
        self.add_log("")
        self.add_log(f"[시작] 봇을 시작합니다...")
        self.add_log(f"[설정] 감시 종목: {TICKER}")
        self.add_log(f"[설정] 체크 주기: {CHECK_SECONDS}초 (10분)")
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
        self.ticker_entry.config(state=tk.NORMAL)
        self.status_label.config(text="🔴 중지됨")
        
        self.add_log("")
        self.add_log("[중지] 봇을 중지합니다...")
        
        # 봇 종료
        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(client.close(), loop)
        
        check_price.cancel()

if __name__ == '__main__':
    root = tk.Tk()
    app = StockBotGUI(root)
    root.mainloop()

