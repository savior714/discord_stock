@echo off
chcp 65001 >nul
title Discord 주가 알람 봇

echo ========================================
echo   Discord 주가 알람 봇 실행
echo ========================================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM 가상 환경 확인 및 활성화
if exist "venv\Scripts\activate.bat" (
    echo [1/3] 가상 환경 활성화 중...
    call venv\Scripts\activate.bat
    echo 가상 환경 활성화 완료
) else if exist ".venv\Scripts\activate.bat" (
    echo [1/3] 가상 환경 활성화 중...
    call .venv\Scripts\activate.bat
    echo 가상 환경 활성화 완료
) else (
    echo [1/3] 가상 환경을 찾을 수 없습니다. 시스템 Python을 사용합니다.
)

echo.

REM .env 파일 확인
if not exist ".env" (
    echo [경고] .env 파일이 없습니다!
    echo env_example.txt를 참고하여 .env 파일을 생성해주세요.
    echo.
    pause
    exit /b 1
)

echo [2/3] .env 파일 확인 완료
echo.

REM 필요한 패키지 설치 확인
echo [3/3] 필요한 패키지 확인 중...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo [오류] 패키지 설치 중 문제가 발생했습니다.
    echo requirements.txt 파일을 확인해주세요.
    echo.
    pause
    exit /b 1
)
echo 패키지 확인 완료
echo.

REM 봇 실행
echo ========================================
echo   봇 시작 중...
echo ========================================
echo.

python main.py

REM 에러 발생 시
if errorlevel 1 (
    echo.
    echo ========================================
    echo   봇 실행 중 오류가 발생했습니다.
    echo ========================================
    echo.
    echo 오류 내용을 확인하고 다음을 점검해주세요:
    echo 1. .env 파일의 토큰과 채널 ID가 올바른지 확인
    echo 2. 인터넷 연결 상태 확인
    echo 3. bot.log 파일에서 상세 오류 확인
    echo.
    pause
    exit /b 1
)

pause

