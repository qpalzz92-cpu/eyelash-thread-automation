# 인수인계 — 캔바 편집본 20개 만들기 (새 세션에서 실행)

## 목적
`lizline-cardnews/content.py`의 **카드뉴스 주제 20개(01~20)**를 **편집 가능한 Canva 디자인**으로 만들고,
그 **링크를 `lizline-cardnews/canva_links.json`에 채워** 노션 "리즈라인 판매점 전용 노하우" DB의
**캔바링크** 열에 들어가게 한다. (원장님이 캔바에서 직접 글자 수정하려면 이게 필요함)

## 왜 새 세션인가
이전 세션은 중간에 Canva MCP 연결이 끊긴 뒤 **그 세션에서 도구를 다시 못 불러왔다**
(계정 커넥터는 `연결됨`인데 세션이 못 읽음). **새 세션은 시작 시 Canva가 붙으므로** 여기서 끝낸다.
→ 먼저 `ToolSearch`로 `mcp__Canva__import-design-from-url`, `mcp__Canva__read-design`가 잡히는지 확인.
   안 잡히면 사용자에게 Canva 커넥터 상태를 확인 요청.

## 준비돼 있는 것 (이미 깃에 있음)
- `lizline-cardnews/content.py` — 주제 20개 (01~10 기존, 11~20 신규)
- `lizline-cardnews/canva/edit_01_*.html ~ edit_20_*.html` — **임포트용 편집본 HTML 20개** (생성 완료)
- `lizline-cardnews/build_import_edit.py` — 위 HTML 생성기 (`python build_import_edit.py`)
- `lizline-cardnews/generate.py` — 완성 PNG 렌더러 (박스/정렬 항상 정확)
- `lizline-cardnews/notion_sales.py` — 노션 발행 (detailed/*.md + out/ 카드 이미지 임베드 + 캔바링크)
- `lizline-cardnews/out/NN_slug/card_1..8.png` — 완성 카드 이미지 20세트

## 실행 순서
1. 편집본 HTML을 최신으로: `cd lizline-cardnews && python build_import_edit.py` → 커밋/푸시.
2. 각 HTML의 **raw URL**을 만든다(공개 저장소):
   `https://raw.githubusercontent.com/qpalzz92-cpu/eyelash-thread-automation/<COMMIT_SHA>/lizline-cardnews/canva/edit_NN_slug.html`
   (브랜치명 대신 **커밋 SHA** 사용 — 안정적)
3. 20개 각각 `mcp__Canva__import-design-from-url(url=<raw>, name="리즈라인 카드뉴스 NN 주제 (편집본)")` 호출 → 결과의 `id`와 `urls` 확보.
4. **캔바링크 URL은 import 결과의 `view_url`(= `https://www.canva.com/d/XXXX`) 형식을 쓸 것.**
   ⚠️ `https://www.canva.com/design/<id>/edit` 형식은 **404 난다. 절대 쓰지 말 것.**
   (`edit_url`은 만료될 수 있으니, 불안하면 `read-design`으로 최신 urls 재확인)
5. `lizline-cardnews/canva_links.json`을 `{"NN_slug": "<view_url>"}` 20개로 채운다.
   (키는 detailed/out 파일명과 동일: 예 `01_upselling`, `11_extend-only`)
6. 커밋/푸시 → `.github/workflows/lizline-notion.yml`가 돌며 노션 캔바링크를 채운다.
   (수동: `python lizline-cardnews/notion_sales.py` — NOTION_TOKEN 필요, 워크플로가 자동 처리)

## 디자인 스펙 (유지)
- 흰 배경, 검정 본문, 강조는 하늘/파랑(#2563EB, #38BDF8).
- `.hl` = 강조(현재 편집본은 흰 글자+파란 배경 하이라이트). 제목·중요어에 사용.
- 하단 우측 "리즈라인" 뱃지 = **가운데 정렬**(generate.py `.handle{...text-align:center}`).
- CTA(8번째 카드) 자동: "공식 판매점 등록·문의 → 리즈라인".

## ⚠️ 중요 주의 — 박스 정렬 이슈
Canva는 HTML을 임포트할 때 **파란 강조 박스를 글자와 별개의 도형으로** 만든다.
- 임포트 직후/내려받기(export)에서는 박스가 글자에 맞게 보인다.
- 그런데 **편집기에서 글자를 수정하면 글자가 재배치되며 박스가 어긋날 수 있다**(별개 도형이라 안 따라옴).
- 선택지: (a) 박스 유지(게시용은 정상, 편집 시 박스 미세조정 필요) /
  (b) `build_import_edit.py`에서 `.hl`을 **파란 글씨(배경 없음)**로 바꾸면 편집해도 절대 안 어긋남.
- **원장님은 '박스 + 편집'을 원함.** 새 세션에서 이 트레이드오프를 다시 안내하고 결정받을 것.
- 참고: 완성 PNG(`generate.py`)는 브라우저 렌더라 박스가 **항상 정확**함(게시는 이걸로 해도 됨).

## 현재 노션 상태
- 20개 행이 "리즈라인 판매점 전용 노하우" DB에 있음(각 페이지 상단에 카드 8장 이미지 임베드).
- **캔바링크 열은 비어 있음**(이전 링크가 404라 제거). → 위 작업으로 채우면 끝.
- 번호 없는 중복 찌꺼기 행("…연락으로…") 1개 있으면 보관처리(archive)로 정리.
