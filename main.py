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

# 환경 변수 로드
load_dotenv()

# ================= 설정값 =================
TOKEN = os.getenv('DISCORD_TOKEN', '여기에_디스코드_봇_토큰')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '123456789012345678'))
TICKER = os.getenv('TICKER', 'AAPL')
CHECK_SECONDS = 600  # 10분 (600초)
# ==========================================

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

plt.switch_backend('Agg')
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# 중복 알람 방지를 위한 상태 저장
last_alert_state = False

def is_active_time():
    """
    현재 시간이 한국 시간(KST) 기준 오전 10시 ~ 새벽 4시 사이인지 확인
    """
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst).time()
    
    start_time = time(10, 0, 0)  # 오전 10시
    end_time = time(4, 0, 0)     # 새벽 4시
    
    # 시간이 자정을 넘어가므로 (10:00 ~ 23:59 OR 00:00 ~ 04:00) 로직 사용
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
    
    # Wilder's smoothing: 첫 값은 단순 평균, 이후는 지수 이동 평균
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    
    # Wilder's smoothing 적용
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
    tp = (df['High'] + df['Low'] + df['Close']) / 3  # Typical Price
    raw_money_flow = tp * df['Volume']
    
    # Positive/Negative Money Flow
    pos_flow = raw_money_flow.where(tp > tp.shift(1), 0)
    neg_flow = raw_money_flow.where(tp < tp.shift(1), 0)
    
    # 14일 이동 합계
    pos_mf = pos_flow.rolling(period).sum()
    neg_mf = neg_flow.rolling(period).sum()
    
    # MFI 계산 (0으로 나누기 방지)
    mfi_ratio = pos_mf / neg_mf
    mfi_ratio = mfi_ratio.replace([np.inf, -np.inf], np.nan)
    mfi = 100 - (100 / (1 + mfi_ratio))
    
    return mfi

def get_data_and_indicators(ticker):
    """
    일봉 데이터와 보조지표 계산
    """
    try:
        # 일봉 데이터 (최소 6개월, 20일 이상 필요)
        df = yf.download(ticker, period='6mo', interval='1d', progress=False)
        
        if df.empty or len(df) < 20:
            logging.warning(f"데이터 부족: {len(df)}개 행만 수신됨")
            return None
        
        # 데이터 정렬 (날짜 오름차순)
        df = df.sort_index()
        
        # NaN 값이 있는 행 제거
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        
        if len(df) < 20:
            logging.warning("NaN 제거 후 데이터 부족")
            return None
        
        # 1. RSI(14) - Wilder's smoothing 사용
        df['RSI'] = calculate_rsi_wilders(df['Close'], period=14)
        
        # 2. MFI(14)
        df['MFI'] = calculate_mfi(df, period=14)
        
        # 3. 볼린저 밴드 (20이동평균, 1표준편차)
        ma20 = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        df['BB_Lower'] = ma20 - (std * 1)
        df['BB_Upper'] = ma20 + (std * 1)
        df['BB_Middle'] = ma20
        
        # 최신 데이터에 NaN이 있는지 확인
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
    현재가가 하단 밴드에 닿았거나 아래에 있는지 확인
    """
    if len(df) < 2:
        return False
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 현재가가 하단 밴드 이하이고, 이전 캔들이 밴드 위에 있었는지 확인
    # 또는 현재가가 하단 밴드에 매우 근접한 경우 (0.1% 이내)
    current_touch = current['Close'] <= current['BB_Lower']
    close_to_lower = abs(current['Close'] - current['BB_Lower']) / current['BB_Lower'] < 0.001
    
    return current_touch or close_to_lower

def draw_chart(df):
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
        
        # 1. 가격 & 볼린저 밴드
        ax1.plot(df_plot.index, df_plot['Close'], color='white', linewidth=2, label='Price')
        ax1.plot(df_plot.index, df_plot['BB_Middle'], color='blue', linestyle='--', alpha=0.7, label='BB Middle (MA20)')
        ax1.plot(df_plot.index, df_plot['BB_Lower'], color='red', linestyle='--', linewidth=1.5, label='BB Lower (1std)')
        ax1.plot(df_plot.index, df_plot['BB_Upper'], color='green', linestyle='--', alpha=0.7, label='BB Upper (1std)')
        ax1.fill_between(df_plot.index, df_plot['BB_Upper'], df_plot['BB_Lower'], color='gray', alpha=0.1)
        ax1.set_title(f'{TICKER} Daily Chart (Last 60 Days)', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylabel('Price', fontsize=10)
        
        # 최신 가격 강조
        latest_price = df_plot['Close'].iloc[-1]
        latest_date = df_plot.index[-1]
        ax1.scatter([latest_date], [latest_price], color='yellow', s=100, zorder=5)
        ax1.annotate(f'{latest_price:.2f}', 
                    xy=(latest_date, latest_price),
                    xytext=(10, 10), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                    fontsize=9)
        
        # 2. RSI
        ax2.plot(df_plot.index, df_plot['RSI'], color='cyan', linewidth=2, label='RSI(14)')
        ax2.axhline(35, color='red', linestyle='--', linewidth=1.5, label='Threshold (35)')
        ax2.axhline(70, color='orange', linestyle=':', alpha=0.5)
        ax2.axhline(30, color='green', linestyle=':', alpha=0.5)
        ax2.fill_between(df_plot.index, 0, 35, color='red', alpha=0.1)
        ax2.set_ylabel('RSI', fontsize=10)
        ax2.set_ylim(0, 100)
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        # 최신 RSI 값 표시
        latest_rsi = df_plot['RSI'].iloc[-1]
        ax2.scatter([latest_date], [latest_rsi], color='cyan', s=50, zorder=5)
        
        # 3. MFI
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
        
        # 최신 MFI 값 표시
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
    global last_alert_state
    
    # 시간 체크: 지정된 시간이 아니면 함수 종료
    if not is_active_time():
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%H:%M:%S")
        logging.debug(f"[{now_kst}] 감시 시간이 아닙니다. (10:00 ~ 04:00 KST)")
        return

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        logging.error(f"채널을 찾을 수 없습니다: {CHANNEL_ID}")
        return

    try:
        df = get_data_and_indicators(TICKER)
        if df is None:
            logging.warning("데이터를 가져올 수 없습니다.")
            return

        today = df.iloc[-1]
        
        # 조건 확인
        cond_mfi = today['MFI'] < 35
        cond_rsi = today['RSI'] < 35
        cond_bb = check_bollinger_touch(df)
        
        all_conditions_met = cond_mfi and cond_rsi and cond_bb
        
        # 로그 출력
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        
        status_icon = "✅" if all_conditions_met else "❌"
        logging.info(
            f"[{now_kst}] {status_icon} {TICKER} | "
            f"Price: {today['Close']:.2f} | "
            f"RSI: {today['RSI']:.2f} {'✓' if cond_rsi else '✗'} | "
            f"MFI: {today['MFI']:.2f} {'✓' if cond_mfi else '✗'} | "
            f"BB: {'✓' if cond_bb else '✗'} "
            f"(Lower: {today['BB_Lower']:.2f})"
        )
        
        # 모든 조건 만족 시 알람 전송 (중복 방지)
        if all_conditions_met:
            if not last_alert_state:  # 이전에 알람을 보내지 않았을 때만
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
                
                chart_buf = draw_chart(df)
                if chart_buf:
                    file = discord.File(chart_buf, filename=f'{TICKER}_chart.png')
                    await channel.send(content=msg, file=file)
                    logging.info(f">>> 알림 전송 완료: {TICKER}")
                else:
                    await channel.send(content=msg)
                    logging.warning("차트 생성 실패, 텍스트만 전송")
                
                last_alert_state = True
            else:
                logging.debug("조건 만족했으나 이미 알람 전송됨 (중복 방지)")
        else:
            # 조건이 해제되면 상태 리셋
            if last_alert_state:
                logging.info(f"조건 해제됨, 다음 알람 준비 완료")
            last_alert_state = False

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

if __name__ == '__main__':
    try:
        client.run(TOKEN)
    except Exception as e:
        logging.error(f"봇 실행 오류: {e}", exc_info=True)

