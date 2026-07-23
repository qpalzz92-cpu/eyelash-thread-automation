#!/usr/bin/env python3
"""
네이버 블로그 "임시저장" 자동화 (로컬 실행 전용).

핵심 원칙
  1) 반드시 "원장님 노트북"에서 실행합니다. (클라우드/서버 X)
     - 낯선 기기·낯선 위치에서 로그인하면 네이버 보안 잠김이 걸립니다.
     - 이 스크립트는 내 노트북에서 돌리니 잠김 위험이 없습니다.
  2) 로그인은 "최초 1회만 직접" 합니다.
     - 세션(쿠키)은 naver_blog/.profile 폴더에 저장돼 다음부터 자동 로그인됩니다.
     - 비밀번호는 코드/파일 어디에도 저장하지 않습니다.
  3) 기본 동작은 "제목 + 본문만 채우고 멈춤" 입니다.
     - 사진을 직접 넣고, 눈으로 확인한 뒤 [저장] 버튼을 직접 누르세요.
     - --auto-save 를 주면 임시저장까지 자동으로 눌러줍니다. (발행은 절대 안 함)

사용법
  cd naver_blog
  pip install -r requirements.txt
  playwright install chromium
  python save_draft.py posts/속눈썹연장창업.txt --blog-id promote3404
  python save_draft.py posts/속눈썹연장창업.txt --blog-id promote3404 --auto-save

글 파일 형식 (posts/*.txt)
  [제목]
  여기에 제목 한 줄
  [본문]
  여기부터 본문...
  (사진) 표시는 그대로 두세요 — 나중에 직접 사진 넣는 자리입니다.
"""
import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = pathlib.Path(__file__).resolve().parent
PROFILE_DIR = ROOT / ".profile"          # 로그인 세션 저장 (git에 안 올라감)
SHOT_PATH = ROOT / "last_run.png"         # 실행 결과 스크린샷


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 글 파일 파싱: [제목] / [본문] 마커로 나눔
# ---------------------------------------------------------------------------
def parse_post(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    if "[제목]" not in text or "[본문]" not in text:
        log("[오류] 글 파일에 [제목] 과 [본문] 마커가 있어야 합니다.")
        sys.exit(1)
    _, rest = text.split("[제목]", 1)
    title_part, body_part = rest.split("[본문]", 1)
    title = title_part.strip()
    # 본문은 줄 구조를 그대로 살린다 (빈 줄 = 문단 간격)
    body_lines = body_part.strip("\n").split("\n")
    if not title:
        log("[오류] 제목이 비어 있습니다.")
        sys.exit(1)
    return title, body_lines


# ---------------------------------------------------------------------------
# 로그인 보장: 로그인 안 돼 있으면 사용자가 직접 로그인할 때까지 대기
# ---------------------------------------------------------------------------
def ensure_logged_in(page, write_url):
    page.goto(write_url, wait_until="domcontentloaded")
    if "nid.naver.com" not in page.url:
        return
    log("")
    log("=" * 56)
    log(" [로그인 필요] 열린 브라우저 창에서 네이버에 직접 로그인하세요.")
    log(" (최초 1회만 하면, 다음부터는 자동 로그인됩니다)")
    log(" 로그인이 끝나면 자동으로 이어집니다...")
    log("=" * 56)
    # 로그인 도메인을 벗어날 때까지 대기 (최대 10분)
    for _ in range(300):
        if "nid.naver.com" not in page.url:
            break
        page.wait_for_timeout(2000)
    page.wait_for_timeout(2000)
    page.goto(write_url, wait_until="domcontentloaded")


# ---------------------------------------------------------------------------
# 방해 팝업 닫기 (이어쓰기 팝업 / 도움말 등)
# ---------------------------------------------------------------------------
def close_popups(frame, page):
    # "작성 중인 글이 있습니다. 이어서 작성하시겠어요?" -> [취소] (새 글로 시작)
    for sel in [
        "button.se-popup-button-cancel",
        ".se-popup-button-cancel",
        "button:has-text('취소')",
    ]:
        try:
            frame.locator(sel).first.click(timeout=2500)
            log("  · 이어쓰기 팝업 닫음 (새 글로 시작)")
            break
        except PWTimeout:
            continue
        except Exception:
            continue
    # 도움말/가이드 레이어가 있으면 닫기 (있을 때만)
    for sel in ["button:has-text('닫기')", ".se-help-panel-close-button"]:
        try:
            frame.locator(sel).first.click(timeout=1500)
        except Exception:
            pass
    page.wait_for_timeout(500)


# ---------------------------------------------------------------------------
# 제목 입력
# ---------------------------------------------------------------------------
def fill_title(page, frame, title):
    for sel in [
        ".se-section-documentTitle .se-text-paragraph",
        ".se-documentTitle",
        ".se-placeholder.__se_placeholder",
    ]:
        try:
            frame.locator(sel).first.click(timeout=4000)
            page.keyboard.insert_text(title)
            log("  · 제목 입력 완료")
            return
        except Exception:
            continue
    raise RuntimeError("제목 입력 영역을 찾지 못했습니다. (에디터 구조 변경 가능성)")


# ---------------------------------------------------------------------------
# 본문 입력 (줄 단위로 넣어 문단 구조 유지)
# ---------------------------------------------------------------------------
def fill_body(page, frame, lines):
    clicked = False
    for sel in [
        ".se-section-text .se-text-paragraph",
        ".se-component.se-text .se-text-paragraph",
        ".se-section-text",
    ]:
        try:
            frame.locator(sel).first.click(timeout=4000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        raise RuntimeError("본문 입력 영역을 찾지 못했습니다. (에디터 구조 변경 가능성)")

    first = True
    for line in lines:
        if not first:
            page.keyboard.press("Enter")
        if line.strip():
            page.keyboard.insert_text(line)
        first = False
    log(f"  · 본문 입력 완료 ({len(lines)}줄)")


# ---------------------------------------------------------------------------
# 임시저장 버튼 클릭 (--auto-save 일 때만)
# ---------------------------------------------------------------------------
def click_save(frame, page):
    for sel in [
        "button.save_btn__bzc5B",
        "[data-click-area='tpb.save']",
        "button:has-text('저장')",
        "text=저장",
    ]:
        try:
            frame.locator(sel).first.click(timeout=3000)
            log("  · [저장] 클릭 → 임시저장 완료")
            page.wait_for_timeout(1500)
            return True
        except Exception:
            continue
    log("  · [경고] 저장 버튼을 자동으로 찾지 못했습니다. 직접 눌러주세요.")
    return False


# ---------------------------------------------------------------------------
def run(post_path, blog_id, auto_save):
    title, body_lines = parse_post(post_path)
    write_url = f"https://blog.naver.com/{blog_id}/postwrite"

    log(f"[글] {title}")
    log(f"[블로그] {blog_id}")
    log(f"[모드] {'임시저장까지 자동' if auto_save else '입력만 (저장은 직접)'}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,                 # 반드시 화면 보이게 (로그인/확인용)
            no_viewport=True,
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            ensure_logged_in(page, write_url)
            log("[진행] 에디터 로딩 대기...")
            page.wait_for_timeout(3000)

            frame = page.frame_locator("#mainFrame")
            close_popups(frame, page)
            fill_title(page, frame, title)
            fill_body(page, frame, body_lines)

            page.screenshot(path=str(SHOT_PATH), full_page=True)
            log(f"[스샷] {SHOT_PATH}")

            if auto_save:
                click_save(frame, page)
            else:
                log("")
                log("=" * 56)
                log(" 입력이 끝났습니다. 브라우저에서 확인하세요.")
                log(" 1) (사진) 자리에 사진을 넣고")
                log(" 2) 소제목을 굵게/크게 잡은 뒤")
                log(" 3) 우측 상단 [저장]을 눌러 임시저장하세요.")
                log("=" * 56)

            log("")
            input(">> 다 됐으면 이 창에서 Enter 를 누르세요. (브라우저 종료) ")
        except Exception as e:
            page.screenshot(path=str(SHOT_PATH), full_page=True)
            log(f"[오류] {e}")
            log(f"[스샷] 실패 화면 저장: {SHOT_PATH}")
            input(">> 화면 확인 후 Enter 로 종료 ")
        finally:
            ctx.close()


def main():
    ap = argparse.ArgumentParser(description="네이버 블로그 임시저장 자동화 (로컬 전용)")
    ap.add_argument("post", help="글 파일 경로 (예: posts/속눈썹연장창업.txt)")
    ap.add_argument("--blog-id", required=True, help="네이버 블로그 아이디 (예: promote3404)")
    ap.add_argument("--auto-save", action="store_true",
                    help="임시저장 버튼까지 자동 클릭 (기본은 입력만)")
    args = ap.parse_args()
    run(args.post, args.blog_id, args.auto_save)


if __name__ == "__main__":
    main()
