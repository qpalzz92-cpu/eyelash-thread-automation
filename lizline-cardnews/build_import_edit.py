# 편집 가능한 Canva import용 HTML 생성(텍스트 요소로 변환).
import sys, generate as g
from content import TOPICS
idx = int(sys.argv[1]) if len(sys.argv)>1 else 1
t = TOPICS[idx-1]
cards = list(t["cards"]) + [g.CTA_CARD]
g._TOTAL = len(cards)
pages = ""
for i, c in enumerate(cards):
    inner = g.RENDERERS[c["type"]](c, i)
    pages += (f'<div data-document-role="page" data-label="{i+1}" '
              f'class="card">{inner}</div>\n')
html = ('<!doctype html><html><head><meta charset="utf-8">'
        f'<style>{g.CSS}</style></head><body>{pages}</body></html>')
import os
os.makedirs("canva", exist_ok=True)
out = f"canva/edit_{idx:02d}_{t['slug']}.html"
open(out,"w",encoding="utf-8").write(html)
print("wrote", out, len(html), "bytes")
