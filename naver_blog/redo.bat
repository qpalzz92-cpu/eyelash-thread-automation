@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Naver Blog Auto Draft (FORCE re-save)
set "BASE=https://github.com/qpalzz92-cpu/eyelash-thread-automation/raw/refs/heads/claude/naver-blog-automation-4rj504/naver_blog"
set "BLOGID=promote3404"

echo ============================================
echo    Naver Blog - FORCE re-save (clean)
echo ============================================
echo.
echo [1/3] Updating program...
curl.exe -L -s -o save_draft.py "%BASE%/save_draft.py"

echo [2/3] Downloading latest posts...
curl.exe -L -s -o "posts\_manifest.txt" "%BASE%/posts/_manifest.txt"
set "ARGS="
for /f "usebackq eol=# tokens=* delims=" %%f in ("posts\_manifest.txt") do (
    curl.exe -L -s -o "posts\%%f" "%BASE%/posts/%%f"
    set "ARGS=!ARGS! posts\%%f"
)

echo [3/3] Re-saving ALL drafts (force). Chrome will open - DO NOT touch.
echo.
python save_draft.py !ARGS! --blog-id %BLOGID% --auto-save --force

echo.
echo ============================================
echo  Done. Check the Naver "temp saved" list.
echo ============================================
pause
