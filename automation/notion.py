#!/usr/bin/env python3
"""
노션 ↔ 스레드 연동.

사용법: python automation/notion.py <mode>
  mode = setup : 노션 페이지 안에 '스레드 콘텐츠 후보' 게시판(DB) 생성 (없을 때만)
         push  : automation/candidates.yaml 의 후보들을 노션 게시판에 추가
         sync  : 노션에서 상태='승인'인 글을 queue.yaml 로 옮김(자동 발행 대상이 됨)
         all   : setup → push → sync 순서로 전부

환경변수: NOTION_TOKEN (필수)
"""
import os
import sys
import json
import datetime
import pathlib

import yaml
import requests

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
ROOT = pathlib.Path(__file__).resolve().parent
CONFIG = ROOT / "notion_config.json"
CANDIDATES = ROOT / "candidates.yaml"
QUEUE = ROOT / "queue.yaml"
STATE = ROOT / "state.json"

TOKEN = os.environ.get("NOTION_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


def log(m):
    print(m, flush=True)


def load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def rt(content):
    """문자열 → Notion rich_text 배열 (2000자 제한 대비 절단)."""
    if not content:
        return []
    return [{"text": {"content": content[:1990]}}]


def plain(prop):
    """Notion 속성(title/rich_text) → 평문 문자열."""
    if not prop:
        return ""
    arr = prop.get("rich_text") or prop.get("title") or []
    return "".join(x.get("plain_text", "") for x in arr)


DB_PROPERTIES = {
    "제목": {"title": {}},
    "상태": {"select": {"options": [
        {"name": "후보", "color": "gray"},
        {"name": "승인", "color": "green"},
        {"name": "발행완료", "color": "blue"},
    ]}},
    "카테고리": {"select": {"options": [
        {"name": n} for n in ["마케팅", "브랜딩", "시스템", "공감", "스토리", "반전", "정보", "전환"]
    ]}},
    "유형": {"select": {"options": [
        {"name": "스토리텔링", "color": "purple"},
        {"name": "데이터", "color": "blue"},
        {"name": "정보성", "color": "green"},
        {"name": "반전", "color": "red"},
    ]}},
    "추천": {"checkbox": {}},
    "주제": {"rich_text": {}},
    "본문": {"rich_text": {}},
    "댓글": {"rich_text": {}},
    "출처": {"rich_text": {}},
    "발행예정일": {"date": {}},
}


def create_database(parent_page_id):
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": "스레드 콘텐츠 후보"}}],
        "properties": DB_PROPERTIES,
    }
    r = requests.post(f"{API}/databases", headers=HEADERS, json=payload, timeout=30)
    if not r.ok:
        raise RuntimeError(f"DB 생성 실패 {r.status_code}: {r.text}")
    return r.json()["id"]


def setup():
    cfg = load_json(CONFIG, {})
    if cfg.get("database_id"):
        log(f"게시판(DB) 이미 있음: {cfg['database_id']}")
        return cfg
    if not cfg.get("parent_page_id"):
        raise RuntimeError("notion_config.json 에 parent_page_id 가 없습니다.")
    dbid = create_database(cfg["parent_page_id"])
    cfg["database_id"] = dbid
    save_json(CONFIG, cfg)
    log(f"게시판(DB) 생성 완료: {dbid}")
    return cfg


def add_row(dbid, c):
    props = {
        "제목": {"title": rt(c["title"])},
        "상태": {"select": {"name": c.get("status", "후보")}},
        "추천": {"checkbox": bool(c.get("recommended"))},
        "주제": {"rich_text": rt(c.get("topic", ""))},
        "본문": {"rich_text": rt(c.get("body", ""))},
        "댓글": {"rich_text": rt(c.get("reply", ""))},
        "출처": {"rich_text": rt(c.get("sources", ""))},
    }
    if c.get("category"):
        props["카테고리"] = {"select": {"name": c["category"]}}
    if c.get("variant"):
        props["유형"] = {"select": {"name": c["variant"]}}
    if c.get("date"):
        props["발행예정일"] = {"date": {"start": c["date"]}}
    r = requests.post(f"{API}/pages", headers=HEADERS,
                      json={"parent": {"database_id": dbid}, "properties": props}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"행 추가 실패 {r.status_code}: {r.text}")
    return r.json()["id"]


def push():
    """candidates.yaml 의 아직 안 올린 후보를 하루 최대 PUSH_LIMIT(기본 3)개까지 노션에 추가."""
    cfg = setup()
    limit = int(os.environ.get("PUSH_LIMIT", "100"))  # 기본: 대기중 후보 전부 한 번에
    data = yaml.safe_load(open(CANDIDATES, encoding="utf-8")) if CANDIDATES.exists() else {}
    cands = (data or {}).get("candidates", [])
    state = load_json(STATE, {"posted": {}})
    pushed = state.setdefault("notion_pushed", [])
    n = 0
    for c in cands:
        key = c.get("key")
        if not key or key in pushed:
            continue
        if n >= limit:
            break
        add_row(cfg["database_id"], c)
        pushed.append(key)
        n += 1
        log(f"노션에 추가: {c['title']}")
    save_json(STATE, state)
    remaining = sum(1 for c in cands if c.get("key") and c["key"] not in pushed)
    log(f"{n}건 추가 완료. (대기중 후보 {remaining}개 남음)")


def query_approved(dbid):
    r = requests.post(f"{API}/databases/{dbid}/query", headers=HEADERS,
                      json={"filter": {"property": "상태", "select": {"equals": "승인"}}}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"조회 실패 {r.status_code}: {r.text}")
    return r.json().get("results", [])


def next_slot(queue_data):
    """queue 내 가장 늦은 예약일 다음 날 21:00(KST)."""
    latest = None
    for p in queue_data.get("posts", []):
        s = p.get("scheduled_at")
        if not s:
            continue
        try:
            d = datetime.datetime.fromisoformat(s).date()
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    base = latest or datetime.date.today()
    return base + datetime.timedelta(days=1)


def block(text):
    return "\n".join("      " + ln if ln else "" for ln in text.rstrip("\n").split("\n"))


def sync():
    cfg = load_json(CONFIG, {})
    dbid = cfg.get("database_id")
    if not dbid:
        log("게시판(DB)이 아직 없습니다. setup 먼저 실행하세요.")
        return
    rows = query_approved(dbid)
    state = load_json(STATE, {"posted": {}})
    synced = state.setdefault("notion_synced", [])

    queue_text = open(QUEUE, encoding="utf-8").read()
    queue_data = yaml.safe_load(queue_text) or {}

    new_blocks = []
    slot = next_slot(queue_data)
    for row in rows:
        pid = row["id"]
        if pid in synced:
            continue
        props = row["properties"]
        title = plain(props.get("제목")) or "제목없음"
        body = plain(props.get("본문"))
        reply = plain(props.get("댓글"))
        if not body:
            log(f"본문 비어있어 건너뜀: {title}")
            continue
        date_prop = props.get("발행예정일", {}).get("date")
        if date_prop and date_prop.get("start"):
            start = date_prop["start"]
            sched = start if "T" in start else f"{start}T21:00:00+09:00"
        else:
            sched = f"{slot.isoformat()}T21:00:00+09:00"
            slot = slot + datetime.timedelta(days=1)
        qid = "notion-" + pid.replace("-", "")[:8]

        entry = [f"  - id: {qid}",
                 f'    title: "{title[:60]}"',
                 f'    scheduled_at: "{sched}"',
                 "    approved: true",
                 "    body: |",
                 block(body)]
        if reply:
            entry.append("    reply: |")
            entry.append(block(reply))
        new_blocks.append("\n".join(entry))
        synced.append(pid)
        log(f"큐에 추가: {title} ({sched[:10]})")

    if new_blocks:
        with open(QUEUE, "a", encoding="utf-8") as f:
            f.write("\n" + "\n\n".join(new_blocks) + "\n")
        save_json(STATE, state)
        log(f"총 {len(new_blocks)}건 큐로 동기화 완료")
    else:
        log("동기화할 승인 글이 없습니다.")


def main():
    if not TOKEN:
        log("ERROR: NOTION_TOKEN 이 설정되지 않았습니다.")
        sys.exit(1)
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "setup":
        setup()
    elif mode == "push":
        push()
    elif mode == "sync":
        sync()
    elif mode == "all":
        setup()
        push()
        sync()
    else:
        log(f"알 수 없는 mode: {mode} (setup/push/sync/all)")
        sys.exit(1)


if __name__ == "__main__":
    main()
