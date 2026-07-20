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
LEARNINGS = ROOT / "learnings.jsonl"

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


def query_all(dbid):
    """DB의 모든 행을 페이지네이션으로 가져온다."""
    results = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        r = requests.post(f"{API}/databases/{dbid}/query", headers=HEADERS, json=payload, timeout=30)
        if not r.ok:
            raise RuntimeError(f"조회 실패 {r.status_code}: {r.text}")
        d = r.json()
        results.extend(d.get("results", []))
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return results


def update_row(page_id, c):
    props = {
        "본문": {"rich_text": rt(c.get("body", ""))},
        "댓글": {"rich_text": rt(c.get("reply", ""))},
        "추천": {"checkbox": bool(c.get("recommended"))},
    }
    r = requests.patch(f"{API}/pages/{page_id}", headers=HEADERS,
                       json={"properties": props}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"행 수정 실패 {r.status_code}: {r.text}")


def archive_row(page_id):
    r = requests.patch(f"{API}/pages/{page_id}", headers=HEADERS,
                       json={"archived": True}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"행 보관 실패 {r.status_code}: {r.text}")


def rebuild(keep_prefixes=("review",)):
    """review-* 를 뺀 노션 행을 전부 보관처리하고, candidates.yaml 로 새로 push.
    (제목이 바뀌어 title 매칭이 안 될 때 깨끗이 재구성)"""
    cfg = load_json(CONFIG, {})
    dbid = cfg.get("database_id")
    if not dbid:
        log("게시판(DB) 없음.")
        return
    data = yaml.safe_load(open(CANDIDATES, encoding="utf-8")) if CANDIDATES.exists() else {}
    cands = (data or {}).get("candidates", [])
    keep_titles = {c["title"] for c in cands
                   if any(c.get("key", "").startswith(p) for p in keep_prefixes)}
    rows = query_all(dbid)
    archived = 0
    for row in rows:
        if plain(row["properties"].get("제목")) not in keep_titles:
            archive_row(row["id"])
            archived += 1
    log(f"{archived}개 행 보관처리")
    # notion_pushed 를 keep 대상만 남기고 초기화 → push 가 나머지를 새로 올림
    state = load_json(STATE, {"posted": {}})
    keep_keys = [c["key"] for c in cands
                 if any(c.get("key", "").startswith(p) for p in keep_prefixes)]
    state["notion_pushed"] = [k for k in state.get("notion_pushed", []) if k in keep_keys]
    save_json(STATE, state)
    push()


def resync(skip_prefixes=("review",)):
    """candidates.yaml 의 후보를 노션에서 제목으로 찾아 본문/댓글/추천을 최신으로 교체.
    skip_prefixes 로 시작하는 key(예: 사용자가 직접 편집한 review-*)는 건너뜀."""
    cfg = load_json(CONFIG, {})
    dbid = cfg.get("database_id")
    if not dbid:
        log("게시판(DB) 없음.")
        return
    rows = query_all(dbid)
    by_title = {plain(row["properties"].get("제목")): row["id"] for row in rows}
    data = yaml.safe_load(open(CANDIDATES, encoding="utf-8")) if CANDIDATES.exists() else {}
    cands = (data or {}).get("candidates", [])
    n = 0
    for c in cands:
        key = c.get("key", "")
        if any(key.startswith(p) for p in skip_prefixes):
            continue
        pid = by_title.get(c["title"])
        if not pid:
            log(f"노션에서 못 찾음(제목 불일치?): {c['title']}")
            continue
        update_row(pid, c)
        n += 1
        log(f"노션 행 수정: {c['title']}")
    log(f"{n}건 노션에서 업데이트 완료 (review 제외)")


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


def record_learning(title, draft_body, draft_reply, final_body, final_reply):
    """내 초안 vs 사용자가 노션에서 고친 최종본을 learnings.jsonl 에 기록(자동 수집)."""
    import json as _json
    entry = {
        "date": now_utc().isoformat(),
        "title": title,
        "draft_body": draft_body, "final_body": final_body,
        "draft_reply": draft_reply, "final_reply": final_reply,
    }
    with open(LEARNINGS, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")


def sync():
    cfg = load_json(CONFIG, {})
    dbid = cfg.get("database_id")
    if not dbid:
        log("게시판(DB)이 아직 없습니다. setup 먼저 실행하세요.")
        return
    rows = query_approved(dbid)
    state = load_json(STATE, {"posted": {}})
    synced = state.setdefault("notion_synced", [])

    # 내 원본 초안(제목→본문/댓글) 맵 — 사용자 수정과 비교해 학습 수집
    cdata = yaml.safe_load(open(CANDIDATES, encoding="utf-8")) if CANDIDATES.exists() else {}
    draft_by_title = {c["title"]: (c.get("body", "").rstrip(), c.get("reply", "").rstrip())
                      for c in (cdata or {}).get("candidates", [])}

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

        # 학습 수집: 내 초안과 사용자 최종본이 다르면 기록
        draft = draft_by_title.get(title)
        if draft and (draft[0].strip() != body.strip() or draft[1].strip() != reply.strip()):
            record_learning(title, draft[0], draft[1], body, reply)
            log(f"  ✎ 수정 감지 → 학습 기록: {title}")

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
    elif mode in ("resync", "update-stories"):
        resync()
    elif mode == "rebuild":
        rebuild()
    elif mode == "all":
        setup()
        push()
        sync()
    else:
        log(f"알 수 없는 mode: {mode} (setup/push/sync/all)")
        sys.exit(1)


if __name__ == "__main__":
    main()
