#!/usr/bin/env python3
"""
스레드 자동 발행 스크립트 (Threads Auto-Post).

동작:
  1) automation/queue.yaml 에서 approved=true 이고 예약시간(scheduled_at)이 지난 글을 찾는다.
  2) 가장 먼저 도래한 글 1개(MAX_POSTS_PER_RUN)를 Threads API로 발행한다.
  3) reply(첫 댓글)가 있으면 본문 게시물에 답글로 단다.
  4) 발행 이력을 automation/state.json 에 기록한다. (queue.yaml 은 사람이 관리하는 원본이라 건드리지 않음)

필요한 환경변수 (GitHub Actions Secrets):
  THREADS_ACCESS_TOKEN : 장기 액세스 토큰
  THREADS_USER_ID      : Threads 사용자 ID (숫자)
선택 환경변수:
  DRY_RUN=true         : 실제 발행 없이 로그만 출력
  MAX_POSTS_PER_RUN=1  : 1회 실행당 발행 개수
  PUBLISH_DELAY=5      : 컨테이너 생성 후 게시까지 대기(초)
  REPLY_DELAY=5        : 본문 게시 후 댓글까지 대기(초)
"""
import os
import sys
import json
import time
import datetime
import pathlib

import yaml
import requests

API = "https://graph.threads.net/v1.0"
ROOT = pathlib.Path(__file__).resolve().parent
QUEUE_PATH = ROOT / "queue.yaml"
STATE_PATH = ROOT / "state.json"


def log(msg):
    print(msg, flush=True)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_dt(value):
    if not value:
        return None
    dt = datetime.datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def load_queue():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("posts", []) or []


def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": {}}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def create_container(user_id, token, text, reply_to_id=None):
    payload = {"media_type": "TEXT", "text": text, "access_token": token}
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id
    resp = requests.post(f"{API}/{user_id}/threads", data=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"컨테이너 생성 실패 {resp.status_code}: {resp.text}")
    return resp.json()["id"]


def publish_container(user_id, token, creation_id):
    payload = {"creation_id": creation_id, "access_token": token}
    resp = requests.post(f"{API}/{user_id}/threads_publish", data=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"게시 실패 {resp.status_code}: {resp.text}")
    return resp.json()["id"]


def post_text(user_id, token, text, reply_to_id=None, publish_delay=5):
    creation_id = create_container(user_id, token, text, reply_to_id=reply_to_id)
    # 메타 권장: 컨테이너 생성 후 잠시 대기 뒤 게시
    time.sleep(publish_delay)
    return publish_container(user_id, token, creation_id)


def pick_due(posts, state):
    posted = state.get("posted", {})
    due = []
    for p in posts:
        pid = p.get("id")
        if not pid or pid in posted:
            continue
        if not p.get("approved"):
            continue
        sched = parse_dt(p.get("scheduled_at"))
        if sched and sched > now_utc():
            continue
        due.append((sched or now_utc(), p))
    due.sort(key=lambda item: item[0])
    return [p for _, p in due]


def main():
    dry_run = os.getenv("DRY_RUN", "false").strip().lower() == "true"
    max_per_run = int(os.getenv("MAX_POSTS_PER_RUN", "1"))
    publish_delay = int(os.getenv("PUBLISH_DELAY", "5"))
    reply_delay = int(os.getenv("REPLY_DELAY", "5"))

    token = os.getenv("THREADS_ACCESS_TOKEN")
    user_id = os.getenv("THREADS_USER_ID")
    if not dry_run and (not token or not user_id):
        log("ERROR: THREADS_ACCESS_TOKEN / THREADS_USER_ID 가 설정되지 않았습니다.")
        sys.exit(1)

    posts = load_queue()
    state = load_state()
    state.setdefault("posted", {})

    due = pick_due(posts, state)
    if not due:
        log("발행할 승인·예정 글이 없습니다. (approved=true 이고 예약시간이 지난 글 없음)")
        return

    published = 0
    for post in due:
        if published >= max_per_run:
            break
        pid = post["id"]
        title = post.get("title", "")
        body = (post.get("body") or "").rstrip()
        reply = (post.get("reply") or "").rstrip()
        log(f"[발행 대상] {pid} — {title}")

        if dry_run:
            log("  (DRY_RUN) 본문 미리보기:")
            log("  " + body.replace("\n", "\n  "))
            if reply:
                log("  (DRY_RUN) 댓글:")
                log("  " + reply.replace("\n", "\n  "))
            state["posted"][pid] = {"dry_run": True, "at": now_utc().isoformat()}
            published += 1
            continue

        media_id = post_text(user_id, token, body, publish_delay=publish_delay)
        reply_id = None
        if reply:
            time.sleep(reply_delay)
            reply_id = post_text(user_id, token, reply, reply_to_id=media_id,
                                 publish_delay=publish_delay)
        state["posted"][pid] = {
            "posted_at": now_utc().isoformat(),
            "thread_post_id": media_id,
            "reply_id": reply_id,
        }
        log(f"  완료 → post_id={media_id}" + (f", reply_id={reply_id}" if reply_id else ""))
        published += 1

    save_state(state)
    log(f"총 {published}건 발행 완료.")


if __name__ == "__main__":
    main()
