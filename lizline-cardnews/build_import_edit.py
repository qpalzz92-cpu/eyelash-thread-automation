# 편집 가능한 Canva import용 HTML 생성 (텍스트가 개별 요소로 들어가는 버전).
# 이미지가 아니라 실제 텍스트/도형으로 변환되어 Canva에서 글자 수정이 됨.
import os, re, sys
import generate as g
from content import TOPICS

# 폰트 base64(@font-face)는 편집본엔 불필요 → 제거해서 파일을 가볍게
CSS = re.sub(r"@font-face\{[^}]*\}", "", g.CSS)

# 편집본 전용: 인라인 강조(.hl)를 '파란 박스'가 아니라 '파란 글씨'로.
# 박스는 글자와 분리된 별개 조각이라 캔바 편집기에서 글자가 재배치되면 틀이 어긋난다.
# 파란 글씨는 글자 자체의 속성이라 절대 틀어지지 않고, 그대로 편집 가능하다.
# (인스타 자동발행용 PNG는 generate.py의 박스 스타일을 그대로 사용 — 여긴 손대지 않음)
CSS += ("\n.hl{background:transparent!important;color:#2563EB!important;"
        "padding:0!important;border-radius:0!important;font-weight:800!important}")

os.makedirs("canva", exist_ok=True)
only = int(sys.argv[1]) if len(sys.argv) > 1 else None
for idx, t in enumerate(TOPICS, 1):
    if only and idx != only:
        continue
    cards = list(t["cards"]) + [g.CTA_CARD]
    g._TOTAL = len(cards)
    pages = ""
    for i, c in enumerate(cards):
        inner = g.RENDERERS[c["type"]](c, i)
        pages += f'<div data-document-role="page" data-label="{i+1}" class="card">{inner}</div>\n'
    html = ('<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{CSS}</style></head><body>{pages}</body></html>')
    out = f"canva/edit_{idx:02d}_{t['slug']}.html"
    open(out, "w", encoding="utf-8").write(html)
    print(f"wrote {out}  ({len(html)} bytes)")
