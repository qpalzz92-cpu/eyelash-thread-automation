@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Naver Blog - Book Promo (promote3404)
set "BASE=https://github.com/qpalzz92-cpu/eyelash-thread-automation/raw/refs/heads/claude/naver-blog-automation-4rj504/naver_blog"
set "BLOGID=promote3404"

echo ============================================
echo    Book Promo - Save to promote3404
echo ============================================
echo.
echo [1/3] Updating program...
curl.exe -L -s -o save_draft.py "%BASE%/save_draft.py"

echo [2/3] Downloading book promo posts...
curl.exe -L -s -o "posts\_manifest_book.txt" "%BASE%/posts/_manifest_book.txt"
set "ARGS="
for /f "usebackq eol=# tokens=* delims=" %%f in ("posts\_manifest_book.txt") do (
    curl.exe -L -s -o "posts\%%f" "%BASE%/posts/%%f"
    set "ARGS=!ARGS! posts\%%f"
)

echo [3/3] A Chrome window will open and LOG OUT.
echo     ^>^> Please LOG IN with the promote3404 account. ^<^<
echo     Then do not touch - it will save 10 posts automatically.
echo.
python save_draft.py !ARGS! --blog-id %BLOGID% --auto-save --switch-account

echo.
echo ============================================
echo  Done. Check promote3404 "temp saved" list.
echo ============================================
pause
