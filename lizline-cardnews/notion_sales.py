#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
판매점 전용 상세 노하우(detailed/*.md)를 노션 DB "리즈라인 판매점 전용 노하우"에 자동 발행.

사용법: python lizline-cardnews/notion_sales.py [push]
환경변수: NOTION_TOKEN (필수)

동작:
  1) 노션에서 DB(제목 매칭) 없으면 부모 페이지 아래에 생성
  2) detailed/*.md 각 문서를 노션 페이지로 upsert
     (제목이 같은 기존 페이지는 보관처리 후 새로 생성 → 항상 최신)
  본문 마크다운(##, ex), - 목록, 문단)을 노션 블록으로 변환.
"""
import os, sys, json, glob, pathlib, re
import requests

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DB_TITLE = "리즈라인 판매점 전용 노하우"
ROOT = pathlib.Path(__file__).resolve().parent
CONFIG = ROOT / "notion_sales_config.json"
DETAILED = ROOT / "detailed"

TOKEN = os.environ.get("NOTION_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


def log(m): print(m, flush=True)


def load_cfg():
    if CONFIG.exists():
        return json.load(open(CONFIG, encoding="utf-8"))
    return {}


def save_cfg(cfg):
    json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def rt(text):
    return [{"type": "text", "text": {"content": text[:1990]}}]


# ---------- 마크다운 → 노션 블록 ----------
def md_to_blocks(md):
    """제목(첫 # 줄)은 title로 반환, 나머지는 블록 리스트로."""
    lines = md.splitlines()
    title = None
    blocks = []
    para = []

    def flush():
        if not para:
            return
        text = "\n".join(para).strip()
        para.clear()
        if not text:
            return
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": rt(text)}})

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip():
            flush(); i += 1; continue
        if ln.startswith("# "):
            flush(); title = ln[2:].strip(); i += 1; continue
        if ln.startswith("## "):
            flush()
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": rt(ln[3:].strip())}})
            i += 1; continue
        if ln.startswith("- "):
            flush()
            while i < len(lines) and lines[i].rstrip().startswith("- "):
                blocks.append({"object": "block", "type": "bulleted_list_item",
                               "bulleted_list_item": {"rich_text": rt(lines[i].rstrip()[2:].strip())}})
                i += 1
            continue
        if ln.startswith("ex)"):
            flush()
            buf = [ln]
            i += 1
            while i < len(lines) and lines[i].strip():
                buf.append(lines[i].rstrip()); i += 1
            blocks.append({"object": "block", "type": "callout",
                           "callout": {"rich_text": rt("\n".join(buf)),
                                       "icon": {"type": "emoji", "emoji": "💬"},
                                       "color": "blue_background"}})
            continue
        para.append(ln)
        i += 1
    flush()
    return title, blocks


# ---------- 노션 API ----------
def search_db():
    r = requests.post(f"{API}/search", headers=HEADERS,
                      json={"query": DB_TITLE, "filter": {"property": "object", "value": "database"}},
                      timeout=30)
    r.raise_for_status()
    for res in r.json().get("results", []):
        t = "".join(x.get("plain_text", "") for x in res.get("title", []))
        if t == DB_TITLE:
            return res["id"]
    return None


def create_db(parent_page_id):
    props = {
        "제목": {"title": {}},
        "카드뉴스": {"rich_text": {}},
        "주제": {"rich_text": {}},
        "상태": {"select": {"options": [
            {"name": "판매점 전용", "color": "blue"},
            {"name": "검토중", "color": "gray"},
        ]}},
    }
    payload = {"parent": {"type": "page_id", "page_id": parent_page_id},
               "title": [{"text": {"content": DB_TITLE}}],
               "icon": {"type": "emoji", "emoji": "💎"},
               "properties": props}
    r = requests.post(f"{API}/databases", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def query_all(dbid):
    out, cursor = [], None
    while True:
        p = {"page_size": 100}
        if cursor:
            p["start_cursor"] = cursor
        r = requests.post(f"{API}/databases/{dbid}/query", headers=HEADERS, json=p, timeout=30)
        r.raise_for_status()
        d = r.json()
        out.extend(d["results"])
        if not d.get("has_more"):
            return out
        cursor = d["next_cursor"]


def title_of(row):
    return "".join(x.get("plain_text", "") for x in row["properties"].get("제목", {}).get("title", []))


def archive(pid):
    requests.patch(f"{API}/pages/{pid}", headers=HEADERS, json={"archived": True}, timeout=30)


def create_page(dbid, title, card_no, slug, blocks):
    props = {
        "제목": {"title": rt(title)},
        "카드뉴스": {"rich_text": rt(f"{card_no}번")},
        "주제": {"rich_text": rt(slug)},
        "상태": {"select": {"name": "판매점 전용"}},
    }
    payload = {"parent": {"database_id": dbid}, "properties": props, "children": blocks[:100]}
    r = requests.post(f"{API}/pages", headers=HEADERS, json=payload, timeout=30)
    if not r.ok:
        raise RuntimeError(f"페이지 생성 실패 {r.status_code}: {r.text}")
    return r.json()["id"]


def main():
    if not TOKEN:
        log("ERROR: NOTION_TOKEN 이 설정되지 않았습니다.")
        sys.exit(1)
    cfg = load_cfg()
    parent = cfg.get("parent_page_id")
    if not parent:
        log("ERROR: notion_sales_config.json 에 parent_page_id 가 필요합니다.")
        sys.exit(1)

    dbid = cfg.get("database_id") or search_db()
    if not dbid:
        dbid = create_db(parent)
        log(f"노션 DB 생성: {dbid}")
    cfg["database_id"] = dbid
    save_cfg(cfg)

    existing = {title_of(r): r["id"] for r in query_all(dbid)}
    files = sorted(glob.glob(str(DETAILED / "*.md")))
    n = 0
    for f in files:
        name = os.path.basename(f)[:-3]          # 01_upselling
        m = re.match(r"(\d+)_(.+)", name)
        card_no = m.group(1) if m else ""
        slug = m.group(2) if m else name
        title, blocks = md_to_blocks(open(f, encoding="utf-8").read())
        title = title or name
        if title in existing:
            archive(existing[title])             # 기존 것 보관 후 최신으로 교체
        create_page(dbid, title, card_no, slug, blocks)
        n += 1
        log(f"노션 발행: [{card_no}] {title}")
    log(f"완료: {n}개 문서 노션에 발행.  DB: {DB_TITLE}")


if __name__ == "__main__":
    main()
