#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
리즈라인 판매점 세일즈 카드뉴스 생성기.
- 디자인(색/레이아웃/폰트)은 고정. 내용(TOPICS)만 갈아끼우면 카드가 자동 생성된다.
- 각 주제: card_1..8.png (풀버전) + card_4_locked.png (인스타 블러 버전).
사용법:  python3 generate.py         (전체 렌더)
         python3 generate.py 2       (2번 주제만)
필요:    lizline-cardnews/fonts/*.woff2 , Chromium (헤드리스)
"""
import base64, os, sys, subprocess, re, html as _html

BASE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(BASE, "fonts")
OUT = os.path.join(BASE, "out")
CHROME = os.environ.get("CHROME_BIN", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# ---------- 폰트 임베드 ----------
_WMAP = {"Regular":400,"Medium":500,"SemiBold":600,"Bold":700,"ExtraBold":800,"Black":900}
def _faces():
    s = ""
    for name, w in _WMAP.items():
        p = os.path.join(FONTS, f"Pretendard-{name}.woff2")
        b = base64.b64encode(open(p,"rb").read()).decode()
        s += (f"@font-face{{font-family:'Pretendard';font-style:normal;font-weight:{w};"
              f"src:url(data:font/woff2;base64,{b}) format('woff2');}}\n")
    return s

CSS = _faces() + """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1350px}
.card{width:1080px;height:1350px;background:#fff;padding:130px 92px 110px;display:flex;flex-direction:column;
 font-family:'Pretendard';color:#14161A;position:relative;overflow:hidden;-webkit-font-smoothing:antialiased}
.card::after{content:"";position:absolute;left:0;bottom:0;width:100%;height:16px;background:linear-gradient(90deg,#2563EB,#38BDF8)}
.mid{flex:1;display:flex;flex-direction:column;justify-content:center}
.bottom{display:flex;align-items:center;justify-content:space-between;margin-top:auto}
.kicker{font-weight:700;font-size:30px;color:#2563EB;letter-spacing:2px;margin-bottom:30px}
.title{font-weight:900;font-size:78px;line-height:1.3;letter-spacing:-1.5px}
.title.sm{font-size:62px}
.hl{background:#2563EB;color:#fff;border-radius:12px;padding:1px 12px;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.blue{color:#2563EB}
.sub{font-weight:500;font-size:40px;line-height:1.5;color:#93A0B4;margin-top:34px}
.sub b{color:#14161A;font-weight:800}
.lead{font-weight:600;font-size:46px;line-height:1.5}
.note{font-weight:600;font-size:38px;line-height:1.55;color:#6B7688;margin-top:30px}
.note b{color:#14161A;font-weight:800}
.badge{display:inline-flex;background:#2563EB;color:#fff;font-weight:800;font-size:30px;padding:14px 32px;border-radius:999px;margin-bottom:38px;align-self:flex-start}
.tag{display:inline-flex;background:#EAF2FF;color:#2563EB;font-weight:800;font-size:30px;padding:12px 26px;border-radius:999px;margin-top:34px}
.item{background:#F1F6FF;border:1.5px solid #E1EAF8;border-radius:26px;padding:32px 38px;display:flex;gap:26px;align-items:center;box-shadow:0 10px 26px rgba(37,99,235,.06)}
.item+.item{margin-top:24px}
.chk{flex:none;width:56px;height:56px;border-radius:50%;background:#2563EB;color:#fff;display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:900}
.item .t{font-weight:700;font-size:37px;line-height:1.35}
.item .t b{color:#2563EB;font-weight:800}
.duo{display:flex;gap:24px;margin-top:14px}
.box{flex:1;background:#F1F6FF;border:1.5px solid #E1EAF8;border-radius:26px;padding:42px 30px;text-align:center}
.box .h{font-weight:900;font-size:48px;color:#2563EB}
.box .d{font-weight:600;font-size:33px;color:#93A0B4;margin-top:14px}
.punch{margin-top:44px;font-weight:900;font-size:58px;text-align:left;line-height:1.3}
.quote{background:#E9F4FF;border-radius:32px;padding:56px 50px;font-weight:800;font-size:50px;line-height:1.45;text-align:left;position:relative}
.quote .qt{transition:none}
.quote.locked .qt{filter:blur(18px)}
.lockpill{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);background:#2563EB;color:#fff;
 font-weight:800;font-size:38px;padding:22px 40px;border-radius:999px;white-space:nowrap;box-shadow:0 12px 30px rgba(37,99,235,.35)}
.ctabtn{background:#2563EB;color:#fff;font-weight:800;font-size:44px;padding:36px 20px;border-radius:22px;text-align:center;margin-top:44px;box-shadow:0 16px 34px rgba(37,99,235,.28)}
.partner{background:#EDF3FF;border-radius:30px;padding:36px 46px;display:inline-flex;align-items:center;gap:30px;align-self:center}
.plogo{flex:none;width:112px;height:112px;border-radius:50%;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:800;font-size:23px;line-height:1.0;color:#1b2a55;letter-spacing:1px;box-shadow:0 8px 22px rgba(37,99,235,.12)}
.plogo small{font-weight:600;font-size:11px;color:#9aa6bd;letter-spacing:0;margin-top:4px}
.pname{font-weight:900;font-size:54px;letter-spacing:-1.5px}
.psub{font-weight:600;font-size:30px;color:#93A0B4;margin-top:8px}
.dots{display:flex;gap:12px;align-items:center}
.dot{width:16px;height:16px;border-radius:50%;background:#D8E1F0}
.dot.on{width:46px;background:#2563EB}
.handle{border:2.5px solid #2563EB;color:#2563EB;font-weight:800;font-size:33px;padding:13px 32px;border-radius:999px}
"""

_TOTAL = 8  # 주제별 카드 수(런타임에 build_topic에서 설정)
def _dots(on):
    return '<div class="dots">'+''.join(
        f'<span class="dot{" on" if i==on else ""}"></span>' for i in range(_TOTAL))+'</div>'
def _bottom(on):
    return f'<div class="bottom">{_dots(on)}<span class="handle">리즈라인</span></div>'

# ---------- 절 단위 자동 줄바꿈 ----------
def br(s):
    """본문이 폭에 맞춰 단어가 뚝 떨어지지 않게, 쉼표/문장 끝에서만 줄을 바꾼다.
    (이미 있는 <br>는 유지). 예: '총액은 비싸 보여도, 쓰는...' -> '총액은 비싸 보여도,<br>쓰는...'"""
    if not s:
        return s
    parts = s.split("<br>")
    parts = [re.sub(r'(?<=[,.])\s+', '<br>', p) for p in parts]
    return "<br>".join(parts)


# ---------- 카드 타입별 렌더 ----------
def _tagrow(text):
    """카테고리 태그(# 앵커링 등)를 항상 같은 위치(뱃지 아래·왼쪽)에 pill로."""
    if not text:
        return ""
    return f'<div style="margin-bottom:34px"><span class="tag" style="margin-top:0">{text}</span></div>'


def _cover(c, dot):
    return (f'<div class="kicker">리즈라인 판매 노하우</div>'
            f'<div class="mid"><div class="title">{c["title"]}</div>'
            f'<div class="sub">{br(c["sub"])}</div></div>{_bottom(dot)}')

def _statement(c, dot):
    lead = f'<div class="lead" style="margin-top:40px">{br(c["lead"])}</div>' if c.get("lead") else ""
    note = f'<div class="note">{br(c["note"])}</div>' if c.get("note") else ""
    title= f'<div class="title">{c["title"]}</div>' if c.get("title") else ""
    return f'<div class="mid">{_tagrow(c.get("tag",""))}{title}{note}{lead}</div>{_bottom(dot)}'

def _point(c, dot):
    boxes = "".join(f'<div class="box"><div class="h">{h}</div><div class="d">{d}</div></div>'
                    for h,d in c["duo"])
    return (f'<div class="badge">{c["badge"]}</div>'
            f'<div class="mid">{_tagrow(c.get("tag",""))}<div class="title">{c["title"]}</div>'
            f'<div class="note">{br(c["note"])}</div>'
            f'<div class="duo">{boxes}</div>'
            f'<div class="punch">{c["punch"]}</div></div>{_bottom(dot)}')

def _mentte(c, dot, locked=False):
    lock = f'<span class="lockpill">공식 판매점 전용 · DM</span>' if locked else ""
    lk = " locked" if locked else ""
    # 노트 끝의 "# 태그"를 뽑아 멘트 박스 위 pill로 올린다
    note = c["note"]
    tag = ""
    if " # " in note:
        note, _, t = note.rpartition(" # ")
        tag = f"# {t}"
    return (f'<div class="badge">{c["badge"]}</div>'
            f'<div class="mid">{_tagrow(tag)}'
            f'<div class="quote{lk}"><span class="qt">{c["quote"]}</span>{lock}</div>'
            f'<div class="note" style="margin-top:40px">{br(note)}</div></div>{_bottom(dot)}')

def _checklist(c, dot):
    items = "".join(f'<div class="item"><div class="chk">✓</div><div class="t">{t}</div></div>'
                    for t in c["items"])
    return (f'<div class="badge">{c["badge"]}</div>'
            f'<div class="mid"><div class="title sm" style="margin-bottom:40px">{c["title"]}</div>'
            f'{items}'
            f'<div class="note" style="margin-top:36px">{br(c["footer"])}</div></div>{_bottom(dot)}')

def _apply(c, dot):
    return (f'<div class="badge">{c["badge"]}</div>'
            f'<div class="mid">{_tagrow(c.get("tag",""))}<div class="lead">{c["lead"]}</div>'
            f'<div class="quote" style="margin-top:44px"><span class="qt">{c["quote"]}</span></div>'
            f'<div class="note">{br(c["note"])}</div></div>{_bottom(dot)}')

def _closer(c, dot):
    return (f'<div class="badge">{c["badge"]}</div>'
            f'<div class="mid">{_tagrow(c.get("tag",""))}<div class="title">{c["title"]}</div>'
            f'<div class="note">{br(c["note"])}</div>'
            f'<div class="punch">{c["punch"]}</div></div>{_bottom(dot)}')

def _cta(c, dot):
    return (f'<div class="mid" style="text-align:center">'
            f'<div class="partner">'
            f'<div class="plogo">Liz line<small>LASH ADDICT PARTNER</small></div>'
            f'<div style="text-align:left"><div class="pname">리즈라인 파트너스</div>'
            f'<div class="psub">래쉬애딕트 판매점 전용방</div></div></div>'
            f'<div class="note" style="text-align:center;margin-top:48px">{br(c["note"])}</div>'
            f'<div class="ctabtn">{c["button"]}</div></div>{_bottom(dot)}')

RENDERERS = {"cover":_cover,"statement":_statement,"point":_point,"mentte":_mentte,
             "checklist":_checklist,"apply":_apply,"closer":_closer,"cta":_cta}

# 모든 주제 공통 CTA 카드
CTA_CARD = {"type":"cta",
            "title":"래쉬애딕트·아이원잇,<br>이렇게 <span class=\"hl\">판매</span>합니다",
            "note":"전체 스크립트·설계법은<br><b>공식 판매점에게만</b> 제공됩니다.",
            "button":"공식 판매점 등록·문의 &nbsp;→&nbsp; 리즈라인"}

def page_html(inner):
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{CSS}</style></head><body><div class="card">{inner}</div></body></html>')

def render_html_to_png(html_str, png_path):
    html_path = png_path[:-4] + ".html"
    open(html_path,"w",encoding="utf-8").write(html_str)
    subprocess.run([CHROME,"--headless=new","--no-sandbox","--disable-gpu","--hide-scrollbars",
                    "--force-device-scale-factor=1","--virtual-time-budget=4000",
                    "--window-size=1080,1350",f"--screenshot={png_path}",html_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def build_topic(idx, topic):
    global _TOTAL
    slug = f'{idx:02d}_{topic["slug"]}'
    d = os.path.join(OUT, slug)
    os.makedirs(d, exist_ok=True)
    cards = list(topic["cards"]) + [CTA_CARD]
    _TOTAL = len(cards)
    for i, c in enumerate(cards):
        dot = i
        inner = RENDERERS[c["type"]](c, dot)
        render_html_to_png(page_html(inner), os.path.join(d, f"card_{i+1}.png"))
        # 인스타 블러 버전: 실전 멘트(mentte) 카드만 잠금 렌더 추가
        if c["type"] == "mentte":
            inner_lock = _mentte(c, dot, locked=True)
            render_html_to_png(page_html(inner_lock), os.path.join(d, f"card_{i+1}_locked.png"))
    return slug

# =====================================================================
#  콘텐츠 — 여기만 고치면 카드가 새로 나온다. (매주 이 리스트만 갱신)
# =====================================================================
from content import TOPICS  # noqa: E402

def main():
    only = None
    if len(sys.argv) > 1:
        only = int(sys.argv[1])
    os.makedirs(OUT, exist_ok=True)
    for i, t in enumerate(TOPICS, 1):
        if only and i != only:
            continue
        slug = build_topic(i, t)
        print(f"[{i:02d}] rendered -> out/{slug}")

if __name__ == "__main__":
    main()
