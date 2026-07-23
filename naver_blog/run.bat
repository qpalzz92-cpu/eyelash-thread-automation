@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 네이버 블로그 임시저장
set "BASE=https://github.com/qpalzz92-cpu/eyelash-thread-automation/raw/refs/heads/claude/naver-blog-automation-4rj504/naver_blog"
set "BLOGID=promote3404"

echo ============================================
echo    네이버 블로그 임시저장 자동화
echo ============================================
echo.
echo [1/3] 최신 프로그램 받는 중...
curl.exe -L -s -o save_draft.py "%BASE%/save_draft.py"

echo [2/3] 최신 글 목록 받는 중...
curl.exe -L -s -o "posts\_manifest.txt" "%BASE%/posts/_manifest.txt"
set "ARGS="
for /f "usebackq eol=# tokens=* delims=" %%f in ("posts\_manifest.txt") do (
    curl.exe -L -s -o "posts\%%f" "%BASE%/posts/%%f"
    set "ARGS=!ARGS! posts\%%f"
)

echo [3/3] 임시저장 시작! 크롬이 열리면 손대지 말고 기다려 주세요.
echo.
python save_draft.py !ARGS! --blog-id %BLOGID% --auto-save

echo.
echo ============================================
echo  다 끝났습니다. 네이버 '임시저장 글' 목록을 확인하세요.
echo  (이미 저장한 글은 자동으로 건너뜁니다)
echo ============================================
echo 창을 닫으려면 아무 키나 누르세요.
pause >nul
