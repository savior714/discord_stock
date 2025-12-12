# Discord 주가 알람 봇

yfinance와 matplotlib을 사용하여 특정 보조지표 조건을 만족할 때 Discord로 알림을 보내는 봇입니다.

## 주요 기능

- **보조지표 모니터링**
  - MFI(14) < 35
  - RSI(14) < 35
  - 볼린저 밴드(20이동평균, 1표준편차) 하단 터치
  - **세 가지 조건을 모두 만족할 때만 알람 발생**

- **일봉 기준** 작동
- **10분 간격** 자동 체크
- **감시 시간**: 한국 시간 오전 10시 ~ 새벽 4시
- **중복 알람 방지**: 같은 조건이 연속으로 발생해도 한 번만 알림

## 설치 방법

### 1. 필요한 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`env_example.txt` 파일을 참고하여 `.env` 파일을 생성하고 값을 수정하세요:

```bash
# Windows
copy env_example.txt .env

# Linux/Mac
cp env_example.txt .env
```

또는 직접 `.env` 파일을 생성하세요.

`.env` 파일 내용:
```
DISCORD_TOKEN=여기에_디스코드_봇_토큰_입력
DISCORD_CHANNEL_ID=123456789012345678
TICKER=AAPL
```

### 3. Discord 봇 토큰 발급

1. [Discord Developer Portal](https://discord.com/developers/applications) 접속
2. New Application 생성
3. Bot 메뉴에서 봇 생성
4. Token 복사하여 `.env` 파일에 입력
5. OAuth2 > URL Generator에서 `bot`과 `Send Messages` 권한 선택
6. 생성된 URL로 봇을 서버에 초대

### 4. 채널 ID 확인

Discord에서 개발자 모드 활성화 후, 알림을 받을 채널에서 우클릭 > ID 복사

## 실행 방법

### Windows (배치 파일 사용 - 권장)

`run_bot.bat` 파일을 더블클릭하거나 실행하세요:

```bash
run_bot.bat
```

배치 파일은 자동으로:
- 가상 환경 활성화 (있는 경우)
- 필요한 패키지 설치 확인
- `.env` 파일 존재 확인
- 봇 실행

### 수동 실행

```bash
python main.py
```

## 로그

봇 실행 중 발생하는 모든 로그는 `bot.log` 파일에 저장됩니다.

## 개선 사항

### 계산 정확도 향상
- **RSI 계산**: Wilder's smoothing 방식 적용 (기존 단순 이동평균 → 정확한 RSI 계산)
- **MFI 계산**: 0으로 나누기 오류 방지 및 정확한 계산 로직 적용
- **볼린저 밴드 터치**: 단순 비교가 아닌 실제 "터치" 조건 확인

### 안정성 개선
- 중복 알람 방지 기능 추가
- 데이터 유효성 검증 강화 (NaN 처리, 데이터 부족 시 처리)
- 상세한 에러 로깅 및 파일 저장

### 사용성 개선
- 환경 변수로 설정 관리 (.env 파일)
- 차트 시각화 개선 (최신 값 강조, 그리드 추가)
- 상세한 로그 출력 (조건 만족 여부 실시간 확인)

## 주의사항

- yfinance는 실시간 데이터가 아닌 지연된 데이터를 제공할 수 있습니다
- 주식 시장이 열려있지 않은 시간에는 최신 데이터가 업데이트되지 않을 수 있습니다
- 한국 주식의 경우 종목 코드에 `.KS` 접미사를 붙이세요 (예: `005930.KS`)

## 라이선스

이 프로젝트는 개인 사용 목적으로 제작되었습니다.

