#!/usr/bin/env python3
"""
네이버 블로그 "임시저장" 자동화 (로컬 실행 전용).

핵심 원칙
  1) 반드시 "내 PC/노트북"에서 실행 (클라우드 X) → 보안 잠김 회피.
  2) 로그인은 최초 1회만 직접. 세션은 naver_blog/.profile 에 저장(자동 로그인).
     비밀번호는 코드/파일에 저장하지 않음.
  3) 기본은 "제목+본문만 채우고 멈춤". --auto-save 주면 임시저장까지(발행은 안 함).

사용법
  python save_draft.py posts/속눈썹연장창업.txt --blog-id promote3404
  python save_draft.py posts/속눈썹연장창업.txt --blog-id promote3404 --auto-save
"""
import argparse
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
PROFILE_DIR = ROOT / ".profile"
SHOT_PATH = ROOT / "last_run.png"
STATE_PATH = ROOT / "state.json"   # 이미 임시저장한 글 기록(중복 방지)


def log(msg):
    print(msg, flush=True)


def load_saved():
    try:
        return set(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def add_saved(name):
    s = load_saved()
    s.add(name)
    try:
        STATE_PATH.write_text(json.dumps(sorted(s), ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 글 파일 파싱: [제목] / [본문]
# ---------------------------------------------------------------------------
def parse_post(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    if "[제목]" not in text or "[본문]" not in text:
        log("[오류] 글 파일에 [제목] 과 [본문] 마커가 있어야 합니다.")
        sys.exit(1)
    _, rest = text.split("[제목]", 1)
    title_part, body_part = rest.split("[본문]", 1)
    title = title_part.strip()
    body_lines = body_part.strip("\n").split("\n")
    if not title:
        log("[오류] 제목이 비어 있습니다.")
        sys.exit(1)
    return title, body_lines


# ---------------------------------------------------------------------------
# 로그인 보장
# ---------------------------------------------------------------------------
def ensure_logged_in(page, write_url):
    page.goto(write_url, wait_until="domcontentloaded")
    if "nid.naver.com" not in page.url:
        return
    log("")
    log("=" * 56)
    log(" [로그인 필요] 열린 브라우저에서 네이버에 직접 로그인하세요.")
    log(" (최초 1회만. 다음부터 자동 로그인)")
    log("=" * 56)
    for _ in range(300):
        if "nid.naver.com" not in page.url:
            break
        page.wait_for_timeout(2000)
    page.wait_for_timeout(2000)
    page.goto(write_url, wait_until="domcontentloaded")


# ---------------------------------------------------------------------------
# 에디터 위치(scope) 자동 판별: #mainFrame 안 or 최상위 페이지
# ---------------------------------------------------------------------------
def get_editor_scope(page):
    """제목 영역이 실제로 존재하는 곳(iframe 또는 page)을 찾아 반환."""
    scopes = []
    try:
        if page.locator("#mainFrame").count() > 0:
            scopes.append(("iframe(#mainFrame)", page.frame_locator("#mainFrame")))
    except Exception:
        pass
    scopes.append(("page(최상위)", page))

    # 최대 20초간, 제목 영역이 잡히는 scope가 나올 때까지 기다림
    for _ in range(20):
        for name, scope in scopes:
            try:
                if scope.locator(".se-section-documentTitle").first.count() > 0:
                    log(f"  · 에디터 위치 감지: {name}")
                    return scope
            except Exception:
                continue
        page.wait_for_timeout(1000)
    log("  · [경고] 제목 영역을 못 찾음 → 최상위 페이지로 진행")
    return page


# ---------------------------------------------------------------------------
# '작성 중인 글이 있습니다' 팝업 닫기 (있으면 [취소])
# ---------------------------------------------------------------------------
def dismiss_draft_popup(scope, page, total_wait_ms=12000):
    waited, step = 0, 800
    while waited < total_wait_ms:
        for finder in (
            lambda: scope.get_by_role("button", name="취소"),
            lambda: scope.locator(".se-popup-button-cancel"),
            lambda: scope.locator("button:has-text('취소')"),
            lambda: scope.locator(".se-popup-button-text:has-text('취소')"),
        ):
            try:
                btn = finder().first
                if btn.is_visible():
                    btn.click(timeout=1500)
                    log("  · 이어쓰기 팝업 [취소] 클릭")
                    page.wait_for_timeout(1000)
                    return True
            except Exception:
                pass
        page.wait_for_timeout(step)
        waited += step
    log("  · 이어쓰기 팝업 못 봄(없거나 이미 닫힘) — 계속 진행")
    return False


def close_help_layers(scope):
    for sel in ["button:has-text('닫기')", ".se-help-panel-close-button"]:
        try:
            scope.locator(sel).first.click(timeout=1000)
        except Exception:
            pass


def normalize_format(scope, page):
    """
    입력 직전, 켜져 있을 수 있는 글자 서식(취소선/굵게/기울임/밑줄)을 끈다.
    (켜진 게 확실할 때만 눌러서, 실수로 서식을 '추가'하지 않도록 보수적으로 동작)
    """
    for name in ("취소선", "굵게", "기울임꼴", "기울임", "밑줄"):
        try:
            btn = scope.get_by_role("button", name=name).first
            if btn.count() == 0:
                continue
            pressed = (btn.get_attribute("aria-pressed") or "")
            cls = (btn.get_attribute("class") or "")
            active = pressed == "true" or any(
                k in cls for k in ("se-is-selected", "-active", "active", "selected")
            )
            if active:
                btn.click()
                page.wait_for_timeout(150)
                log(f"  · 서식 끔: {name}")
        except Exception:
            continue


# ---------------------------------------------------------------------------
# 제목 입력
# ---------------------------------------------------------------------------
def fill_title(page, scope, title):
    selectors = [
        ".se-section-documentTitle .se-text-paragraph",
        ".se-documentTitle .se-text-paragraph",
        ".se-title-text .se-text-paragraph",
        ".se-section-documentTitle",
        ".se-documentTitle",
    ]
    last_err = None
    for _ in range(2):
        for sel in selectors:
            try:
                scope.locator(sel).first.click(timeout=3000)
                normalize_format(scope, page)
                page.keyboard.insert_text(title)
                log("  · 제목 입력 완료")
                return
            except Exception as e:
                last_err = e
                continue
        dismiss_draft_popup(scope, page, total_wait_ms=4000)
    raise RuntimeError(f"제목 입력 영역을 찾지 못했습니다. (마지막 오류: {last_err})")


# ---------------------------------------------------------------------------
# 본문 입력 (줄 단위 → 문단 구조 유지)
# ---------------------------------------------------------------------------
def fill_body(page, scope, lines):
    selectors = [
        ".se-section-text .se-text-paragraph",
        ".se-component.se-text .se-text-paragraph",
        ".se-section-text",
        ".se-content .se-text-paragraph",
    ]
    clicked = False
    for _ in range(2):
        for sel in selectors:
            try:
                scope.locator(sel).first.click(timeout=3000)
                clicked = True
                break
            except Exception:
                continue
        if clicked:
            break
        dismiss_draft_popup(scope, page, total_wait_ms=4000)
    if not clicked:
        raise RuntimeError("본문 입력 영역을 찾지 못했습니다.")

    # 입력 직전 서식(취소선 등) 끄기 → 본문에 줄 안 생기게
    normalize_format(scope, page)

    first = True
    for line in lines:
        if not first:
            page.keyboard.press("Enter")
        if line.strip():
            page.keyboard.insert_text(line)
        first = False
    log(f"  · 본문 입력 완료 ({len(lines)}줄)")


# ---------------------------------------------------------------------------
# 임시저장 (--auto-save)
# ---------------------------------------------------------------------------
def click_save(scope, page):
    for finder in (
        lambda: scope.get_by_role("button", name="저장"),
        lambda: scope.locator("button:has-text('저장')"),
        lambda: scope.locator("[class*=save]"),
    ):
        try:
            finder().first.click(timeout=3000)
            log("  · [저장] 클릭 → 임시저장 완료")
            page.wait_for_timeout(1500)
            return True
        except Exception:
            continue
    log("  · [경고] 저장 버튼 자동 클릭 실패 — 직접 [저장]을 눌러주세요.")
    return False


# ---------------------------------------------------------------------------
def process_one(page, post_path, auto_save):
    title, body_lines = parse_post(post_path)
    log(f"\n[글] {title}")
    scope = get_editor_scope(page)
    dismiss_draft_popup(scope, page)
    close_help_layers(scope)
    fill_title(page, scope, title)
    fill_body(page, scope, body_lines)
    page.screenshot(path=str(SHOT_PATH), full_page=True)
    if auto_save:
        click_save(scope, page)
    return title


def run(post_paths, blog_id, auto_save, force=False):
    write_url = f"https://blog.naver.com/{blog_id}/postwrite"

    # 자동 저장 모드면, 이미 저장한 글은 건너뛴다(중복 방지). --force 면 무시.
    if auto_save and not force:
        saved = load_saved()
        remaining = [p for p in post_paths if pathlib.Path(p).name not in saved]
        skipped = len(post_paths) - len(remaining)
        if skipped:
            log(f"[안내] 이미 저장된 {skipped}편은 건너뜁니다. (다시 하려면 --force)")
        post_paths = remaining

    if not post_paths:
        log("[안내] 새로 저장할 글이 없습니다. (모두 이미 저장됨)")
        return

    log(f"[블로그] {blog_id}")
    log(f"[글 개수] {len(post_paths)}편")
    log(f"[모드] {'임시저장까지 자동' if auto_save else '입력만 (저장은 직접)'}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            no_viewport=True,
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        done, failed = [], []
        try:
            ensure_logged_in(page, write_url)
            for i, pp in enumerate(post_paths):
                # 두 번째 글부터는 새 글쓰기 화면을 새로 연다
                if i > 0:
                    page.goto(write_url, wait_until="domcontentloaded")
                log(f"[진행] ({i + 1}/{len(post_paths)}) 에디터 로딩 대기...")
                page.wait_for_timeout(4000)
                try:
                    title = process_one(page, pp, auto_save)
                    done.append(title)
                    if auto_save:
                        add_saved(pathlib.Path(pp).name)
                    log(f"  ✅ 완료: {pp}")
                except Exception as e:
                    failed.append(pp)
                    try:
                        page.screenshot(path=str(SHOT_PATH), full_page=True)
                    except Exception:
                        pass
                    log(f"  ⚠️ 실패: {pp} → {e}")

            log("")
            log("=" * 56)
            log(f" 총 {len(post_paths)}편 중 {len(done)}편 처리 완료")
            if failed:
                log(f" 실패 {len(failed)}편: {', '.join(failed)}")
            if auto_save:
                log(" → 네이버 '임시저장 글' 목록에서 확인하세요.")
                log(" → 나중에 열어서 (사진) 자리에 사진 넣고 발행하면 끝!")
            else:
                log(" → 각 글을 확인하고 [저장]을 눌러주세요.")
            log("=" * 56)
            log("")
            input(">> 다 됐으면 여기서 Enter (브라우저 종료) ")
        finally:
            ctx.close()


def main():
    ap = argparse.ArgumentParser(description="네이버 블로그 임시저장 자동화 (로컬 전용)")
    ap.add_argument("post", nargs="*", help="글 파일 경로 (여러 개 가능)")
    ap.add_argument("--all", action="store_true", help="posts 폴더의 모든 .txt 자동 처리")
    ap.add_argument("--blog-id", required=True, help="네이버 블로그 아이디 (예: promote3404)")
    ap.add_argument("--auto-save", action="store_true", help="임시저장까지 자동")
    ap.add_argument("--force", action="store_true", help="이미 저장한 글도 다시 저장")
    args = ap.parse_args()

    if args.all:
        # '_' 로 시작하는 파일(_manifest 등)은 글이 아니므로 제외
        posts = [str(p) for p in sorted((ROOT / "posts").glob("*.txt"))
                 if not p.name.startswith("_")]
        auto_save = True
    elif args.post:
        posts = args.post
        auto_save = args.auto_save or len(posts) > 1  # 여러 편이면 자동 저장
    else:
        ap.error("글 파일을 지정하거나 --all 을 쓰세요.")
        return

    if not posts:
        log("[오류] 처리할 글이 없습니다.")
        sys.exit(1)
    run(posts, args.blog_id, auto_save, force=args.force)


if __name__ == "__main__":
    main()
