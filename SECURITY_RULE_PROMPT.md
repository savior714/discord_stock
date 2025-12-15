# 🔐 Git 커밋 전 민감 정보 검사 규칙

## Global Rule 프롬프트

다음 프롬프트를 Cursor의 Global Rules에 추가하세요:

```
# 🔐 보안 규칙: 민감한 정보 커밋 방지

코드를 커밋하거나 파일을 수정하기 전에 반드시 다음을 확인하세요:

## 필수 검사 항목

### 1. Discord 토큰 및 API 키 검사
- `DISCORD_TOKEN=`, `API_KEY=`, `SECRET=`, `PASSWORD=` 등의 환경 변수에 실제 값이 있는지 확인
- Discord 토큰 패턴: `MTQ0...` 또는 `ODg0...` 같은 Base64 인코딩된 긴 문자열 (50자 이상)
- 실제 토큰은 반드시 `.env` 파일에만 저장하고, `env_example.txt`에는 예제 값만 사용
- 예제 값: `여기에_디스코드_봇_토큰_입력` 또는 `YOUR_TOKEN_HERE`

### 2. 채널 ID 및 개인 식별자 검사
- `DISCORD_CHANNEL_ID=` 뒤에 실제 18자리 숫자 ID가 있는지 확인
- 실제 채널 ID는 `env_example.txt`에 포함하지 말고 예제 값(`123456789012345678`)만 사용
- 실제 사용자 ID, 서버 ID 등도 커밋하지 않음

### 3. 파일별 검사 규칙
- `env_example.txt`: 반드시 예제 값만 포함 (실제 토큰/ID 절대 금지)
- `.env`: 절대 커밋하지 않음 (이미 .gitignore에 포함되어 있어야 함)
- `*.json`: 실행 중 생성되는 데이터 파일은 커밋하지 않음
- `bot.log`: 로그 파일에 토큰이 포함될 수 있으므로 커밋하지 않음

### 4. 커밋 전 자동 검사
커밋하기 전에 다음 패턴을 검색하여 실제 값이 있는지 확인:
- `DISCORD_TOKEN=[A-Za-z0-9._-]{50,}` (실제 토큰 패턴)
- `DISCORD_CHANNEL_ID=[0-9]{18,}` (실제 채널 ID 패턴)
- `DISCORD_TOKEN=MTQ` 또는 `DISCORD_TOKEN=ODg` (Discord 토큰 시작 패턴)

### 5. 발견 시 조치
실제 토큰이나 민감한 정보를 발견하면:
1. 즉시 커밋을 중단
2. 해당 값을 예제 값으로 교체
3. 이미 커밋되었다면 토큰을 즉시 재생성 (Discord Developer Portal)
4. Git 히스토리에서 제거 필요 시 `git filter-branch` 사용 고려

## 예제 값 형식
✅ 올바른 예제:
```
DISCORD_TOKEN=여기에_디스코드_봇_토큰_입력
DISCORD_CHANNEL_ID=123456789012345678
```

❌ 잘못된 예제 (실제 값처럼 보이는 값 - 절대 사용 금지):
```
DISCORD_TOKEN=FAKE_TOKEN_DO_NOT_USE_1234567890.ABCDEFGHIJKLMNOPQRSTUVWXYZ.1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ
DISCORD_CHANNEL_ID=999999999999999999
```

## 특별 주의 파일
- `env_example.txt`: 항상 예제 값만 포함
- `.env`: 절대 커밋하지 않음
- 모든 설정 파일: 실제 값 대신 예제 값 사용
```

## 사용 방법

1. Cursor 설정 열기
2. Global Rules 섹션에 위 프롬프트 추가
3. 저장 후 적용

이 규칙은 모든 코드 편집 및 커밋 전에 자동으로 적용됩니다.

