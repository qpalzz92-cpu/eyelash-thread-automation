#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
리즈라인 인스타그램 자동 발행 (공식 Instagram Graph API, 캐러셀).
매주 금요일, posting_schedule.yaml 의 approved:true 주제를 위에서부터 하나씩 발행한다.
인스타에는 4번 카드를 블러 버전(card_4_locked)으로 올린다.

필요 환경변수(깃허브 시크릿):
  IG_USER_ID        인스타그램 비즈니스 계정 ID
  IG_ACCESS_TOKEN   장기 액세스 토큰(instagram_content_publish 권한)
선택:
  GRAPH_VERSION     (기본 v21.0)
  DRY_RUN=true      실제 발행 없이 계획만 출력
  GITHUB_REPOSITORY / GITHUB_REF_NAME  (CI에서 raw 이미지 URL 구성용)

사용: python instagram_publish.py
"""
import os, sys, json, time, pathlib
import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parent
SCHEDULE = ROOT / "posting_schedule.yaml"
STATE = ROOT / "instagram_state.json"
OUT = ROOT / "out"

IG_USER_ID = os.environ.get("IG_USER_ID")
TOKEN = os.environ.get("IG_ACCESS_TOKEN")
VER = os.environ.get("GRAPH_VERSION", "v21.0")
DRY = os.environ.get("DRY_RUN", "").lower() == "true"
GRAPH = f"https://graph.facebook.com/{VER}"

# 인스타에 올릴 카드 순서 (4번은 블러 버전)
CARD_ORDER = ["card_1", "card_2", "card_3", "card_4_locked",
              "card_5", "card_6", "card_7", "card_8"]

# 주제별 제목/첫 줄 훅 (캡션 생성용)
TITLES = {
    "01_upselling": "객단가 2배, ‘하나 더’ 파는 업셀링",
    "02_price-objection": "‘비싸요’를 구매로 바꾸는 가격 응대",
    "03_repurchase": "한 번 산 고객을 재구매로",
    "04_no-effect": "‘효과 없어요’를 재구매로 되돌리기",
    "05_standalone-demand": "영양제만 사러 오게 만드는 법",
    "06_dm-closing": "‘생각해볼게요’ 고객 되살리기",
    "07_review-leverage": "후기 1장으로 신규+재구매",
    "08_opening-line": "진열대 앞 3초, 오프닝 한마디",
    "09_gentle-delivery": "상처 안 주고 권하는 법",
    "10_instore-3touch": "SNS 없이 매장에서만 파는 법",
}
HOOKS = {
    "01_upselling": "속눈썹 영양제 하나 팔고 끝? 객단가 2배 만드는 원장님은 여기서 ‘하나 더’를 붙입니다.",
    "02_price-objection": "“비싸요”는 거절이 아니라 질문이에요. 여기서 무너지지 마세요.",
    "03_repurchase": "영양제 매출의 진짜 승부는 ‘두 번째 구매’에서 갈립니다.",
    "04_no-effect": "“효과 없어요” 하는 고객, 대부분 사용법 문제예요. 환불 말고 재구매로.",
    "05_standalone-demand": "시술 안 하는 날에도 매출이 도는 샵, 뭐가 다를까요?",
    "06_dm-closing": "“생각해볼게요” 하고 나간 고객, 카톡 한 통으로 되살립니다.",
    "07_review-leverage": "잘 찍은 후기 1장이 광고 10개보다 셉니다.",
    "08_opening-line": "영양제는 설명이 아니라 ‘한 문장’으로 팔려요.",
    "09_gentle-delivery": "“상하셨네요” 이 한마디가 판매를 망칩니다.",
    "10_instore-3touch": "SNS 안 해도 영양제 잘 파는 샵의 비밀.",
}
HASHTAGS = ("#속눈썹영양제 #래쉬애딕트 #아이원잇 #속눈썹연장 #속눈썹펌 "
            "#속눈썹샵 #뷰티창업 #1인샵 #리즈라인 #속눈썹연장창업")


def log(m): print(m, flush=True)


def raw_base():
    repo = os.environ.get("GITHUB_REPOSITORY", "qpalzz92-cpu/eyelash-thread-automation")
    ref = os.environ.get("GITHUB_REF_NAME", "claude/eyelash-supplement-sales-content-pru1oc")
    return f"https://raw.githubusercontent.com/{repo}/{ref}/lizline-cardnews/out"


def caption(slug):
    return (f"{HOOKS.get(slug,'')}\n\n"
            f"원장님들이 실제로 쓰는 판매 노하우, 이번 편은 「{TITLES.get(slug,'')}」\n\n"
            "· 저장해두고 상담 전에 한 번씩 보세요\n"
            "· 4·5번 실제 멘트는 공식 판매점 전용 자료로 풀버전 제공해요\n\n"
            "래쉬애딕트·아이원잇 공식 판매점 등록·문의 👉 프로필 링크 / DM\n\n"
            f"{HASHTAGS}")


def load_state():
    if STATE.exists():
        return json.load(open(STATE, encoding="utf-8"))
    return {"posted": []}


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(STATE, "a", encoding="utf-8").write("\n")


def pick_next(posted):
    data = yaml.safe_load(open(SCHEDULE, encoding="utf-8")) if SCHEDULE.exists() else {}
    for item in (data or {}).get("posts", []):
        slug = item.get("slug")
        if item.get("approved") and slug and slug not in posted:
            return slug
    return None


def _post(url, params):
    r = requests.post(url, params=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"IG API 실패 {r.status_code}: {r.text}")
    return r.json()


def publish(slug):
    base = raw_base()
    images = [f"{base}/{slug}/{name}.png" for name in CARD_ORDER]
    cap = caption(slug)
    log(f"발행 대상: {slug}  (이미지 {len(images)}장)")
    if DRY:
        log("[DRY_RUN] 실제 발행 안 함. 캡션 미리보기:\n" + cap)
        for u in images:
            log("  " + u)
        return "dry-run"

    # 1) 캐러셀 아이템 컨테이너 생성
    child_ids = []
    for u in images:
        j = _post(f"{GRAPH}/{IG_USER_ID}/media",
                  {"image_url": u, "is_carousel_item": "true", "access_token": TOKEN})
        child_ids.append(j["id"])
        time.sleep(1)
    # 2) 캐러셀 컨테이너 생성
    carousel = _post(f"{GRAPH}/{IG_USER_ID}/media",
                     {"media_type": "CAROUSEL", "children": ",".join(child_ids),
                      "caption": cap, "access_token": TOKEN})
    # 3) 발행
    time.sleep(2)
    pub = _post(f"{GRAPH}/{IG_USER_ID}/media_publish",
                {"creation_id": carousel["id"], "access_token": TOKEN})
    log(f"발행 완료. media id = {pub.get('id')}")
    return pub.get("id")


def main():
    if not TOKEN or not IG_USER_ID:
        log("IG_ACCESS_TOKEN / IG_USER_ID 미설정 → 발행 스킵 (시크릿 세팅 후 자동 시작).")
        return  # 아직 미설정이면 조용히 넘어감(스케줄 실패 방지)
    state = load_state()
    slug = pick_next(state["posted"])
    if not slug:
        log("발행할 승인 주제가 없습니다. (posting_schedule.yaml 확인)")
        return
    mid = publish(slug)
    if mid and mid != "dry-run":
        state["posted"].append(slug)
        save_state(state)
        log(f"상태 기록: {slug} 발행 완료")


if __name__ == "__main__":
    main()
