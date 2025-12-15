# 인코딩 가이드 (Encoding Guide)

## 문제 원인 분석

### 왜 한글이 깨지는가?

1. **Windows 기본 인코딩**: Windows는 기본적으로 CP949 (EUC-KR) 인코딩을 사용
2. **PowerShell 인코딩**: PowerShell은 기본적으로 UTF-16 LE (BOM 포함)로 파일 저장
3. **Python 기본 동작**: Python 3.x는 UTF-8을 기본으로 사용하지만, Windows에서는 시스템 로케일 따름
4. **Git 동작**: Git은 기본적으로 파일 인코딩을 변경하지 않지만, 줄바꿈 문자는 변환 가능

### 발생 시나리오

```
PowerShell에서 파일 생성
    ↓ (UTF-16 LE 또는 시스템 인코딩)
파일 저장
    ↓
Python으로 읽기 시도
    ↓ (UTF-8로 읽으려고 시도)
한글 깨짐 발생! (硫붿씤, 梨꾨꼸 등)
```

## 해결 방법

### 1. 모든 파일을 UTF-8 (BOM 없이)로 저장

**Python에서 파일 저장:**
```python
# 올바른 방법
with open('file.txt', 'w', encoding='utf-8') as f:
    f.write(content)

# 잘못된 방법 (시스템 기본 인코딩 사용)
with open('file.txt', 'w') as f:  # ❌
    f.write(content)
```

**PowerShell에서 파일 저장:**
```powershell
# 올바른 방법
$content | Out-File -FilePath file.txt -Encoding UTF8

# 또는 Python 사용
python -c "with open('file.txt', 'w', encoding='utf-8') as f: f.write('내용')"
```

### 2. Git 설정 (.gitattributes)

`.gitattributes` 파일로 인코딩과 줄바꿈 통일:
```gitattributes
*.py text eol=lf encoding=UTF-8
*.md text eol=lf encoding=UTF-8
*.txt text eol=lf encoding=UTF-8
*.json text eol=lf encoding=UTF-8
*.env text eol=lf encoding=UTF-8
```

### 3. 에디터 설정

**VS Code / Cursor:**
- 파일 → 기본 설정 → 설정
- `files.encoding`: `utf8`
- `files.eol`: `\n` (LF)
- `files.autoGuessEncoding`: `false`

## Cursor AI Global Rule

다음 프롬프트를 Cursor AI의 `.cursorrules` 또는 Global Rules에 추가하세요:

```
# File Encoding Rules

## Always use UTF-8 encoding without BOM for all text files

1. **Python File Operations:**
   - ALWAYS specify `encoding='utf-8'` when opening files
   - Example: `open('file.txt', 'r', encoding='utf-8')`
   - Never rely on system default encoding

2. **File Creation:**
   - All text files (.py, .md, .txt, .json, .env, etc.) must be UTF-8 encoded
   - No BOM (Byte Order Mark) should be added
   - Use LF (\n) line endings for cross-platform compatibility

3. **Shell Commands:**
   - When creating files via shell commands, ensure UTF-8 encoding
   - For PowerShell: Use `Out-File -Encoding UTF8` or Python scripts
   - For Bash: UTF-8 is usually default, but verify with `locale`

4. **Git Configuration:**
   - Always include `.gitattributes` file in projects
   - Specify text file types and their encodings
   - Normalize line endings across platforms

5. **Korean/Chinese/Japanese Text:**
   - UTF-8 is MANDATORY for non-ASCII characters
   - Test file reading/writing with actual Korean text
   - Verify encoding in editor before committing

6. **Console Output:**
   - Be aware that Windows console may not display UTF-8 correctly
   - File encoding is correct even if console display is garbled
   - Use `chcp 65001` in cmd.exe for UTF-8 console output

## Example Code Pattern

```python
# ✅ CORRECT - Always specify encoding
with open('file.txt', 'w', encoding='utf-8') as f:
    f.write('한글 텍스트')

with open('file.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# ❌ WRONG - System default encoding (may cause issues)
with open('file.txt', 'w') as f:
    f.write('한글 텍스트')
```

## Verification

Before committing files with Korean text:
1. Open file in hex editor and verify UTF-8 encoding (no BOM: EF BB BF)
2. Check that Korean characters display correctly in multiple editors
3. Verify Git diff shows correct Korean characters
4. Test file reading in Python with explicit UTF-8 encoding
```

## 프로젝트별 체크리스트

새 프로젝트 시작 시:
- [ ] `.gitattributes` 파일 생성
- [ ] 에디터 인코딩 설정 확인 (UTF-8)
- [ ] Python 파일 열기 시 항상 `encoding='utf-8'` 명시
- [ ] 한글 포함 파일 커밋 전 인코딩 확인
- [ ] README에 인코딩 가이드 추가

## 트러블슈팅

### 문제: 한글이 깨져 보임
```
硫붿씤 梨꾨꼸 (RSI + MFI + 蹂쇰┛? 諛대뱶)
```

**해결:**
1. 파일을 UTF-8로 다시 저장
2. Python 스크립트로 변환:
   ```python
   with open('file.txt', 'r', encoding='utf-8') as f:
       content = f.read()
   with open('file.txt', 'w', encoding='utf-8') as f:
       f.write(content)
   ```

### 문제: PowerShell에서 한글이 깨짐
**원인:** PowerShell 콘솔의 코드 페이지가 CP949
**해결:** 파일 자체는 UTF-8로 저장되었으므로 문제없음 (콘솔 표시만 깨짐)

### 문제: Git diff에서 한글이 깨짐
**해결:**
```bash
git config --global core.quotepath false
git config --global i18n.commitencoding utf-8
git config --global i18n.logoutputencoding utf-8
```

## 참고 자료

- [Python Unicode HOWTO](https://docs.python.org/3/howto/unicode.html)
- [Git Attributes](https://git-scm.com/docs/gitattributes)
- [UTF-8 Everywhere Manifesto](http://utf8everywhere.org/)
