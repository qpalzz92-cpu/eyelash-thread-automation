# 스레드 자동 발행 세팅 가이드

> 코드+GitHub Actions로 스레드에 자동 발행하는 시스템의 설치·운영 가이드.
> **당신이 직접 할 일은 딱 하나 — 토큰 2개 발급해서 GitHub에 넣기.** 나머지 코드는 다 준비돼 있어요.

---

## 전체 구조 (한눈에)

```
queue.yaml  ──approved:true & 예약시간 도달──►  post_to_threads.py  ──►  Threads API (자동 발행)
    ▲                                                    │
 사람이 검토·승인                                    state.json (발행 이력 기록)
                         GitHub Actions가 하루 2번 자동 실행 (밤 9시 / 점심 12시 반)
```

- **초반 20개(검토 단계)**: `queue.yaml`의 글을 확인하고 `approved: true`로 바꾼 것만 발행됨.
- **이후(자동 단계)**: 새 글을 approved 상태로 넣어두면 예약 시간에 알아서 발행.

---

## STEP 1. 인스타그램을 프로페셔널 계정으로 전환

Threads API는 프로페셔널(비즈니스/크리에이터) 계정에서만 동작해요.
- 인스타 앱 → 설정 → 계정 → **프로페셔널 계정으로 전환**

## STEP 2. 메타 개발자 앱 만들기

1. https://developers.facebook.com 접속 → 우상단 **로그인**(위 인스타와 연결된 페북/메타 계정).
2. **My Apps → Create App** → 사용 사례에서 **"Access the Threads API"** 선택.
3. 앱 이름 아무거나 정하고 생성.

## STEP 3. Threads API 권한 추가 + 계정 연결

1. 만든 앱 → **Threads API** 설정으로 이동.
2. 권한(스코프)에서 아래 2개를 추가:
   - `threads_basic`
   - `threads_content_publish`
3. **Threads 계정 연결(Add/Connect account)** → 본인 스레드 계정 연결.
4. 본인 계정을 앱의 **테스터/개발자**로 두면 앱 심사(App Review) 없이 본인 계정엔 바로 발행 가능해요.

## STEP 4. 액세스 토큰 발급 (그리고 장기 토큰으로 교환)

1. Threads API 설정 화면에서 **Generate access token** → 단기 토큰이 나옵니다.
2. 이걸 **장기(long-lived, 60일) 토큰**으로 교환하세요. 브라우저 주소창에 아래를 붙여넣고 실행:
   ```
   https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=<앱시크릿>&access_token=<단기토큰>
   ```
   - `<앱시크릿>`: 앱 설정 → 기본 설정(App Secret)
   - 응답의 `access_token` 값이 **장기 토큰**입니다. 이게 `THREADS_ACCESS_TOKEN`.

> 장기 토큰은 60일마다 갱신이 필요해요. 갱신 자동화는 나중에 붙일 수 있습니다(아래 '운영 팁' 참고).

## STEP 5. 내 Threads 사용자 ID 확인

브라우저 주소창에 붙여넣고 실행:
```
https://graph.threads.net/v1.0/me?fields=id,username&access_token=<장기토큰>
```
- 응답의 `id` 숫자가 `THREADS_USER_ID` 입니다.

## STEP 6. GitHub에 비밀값(Secrets) 등록

GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
아래 2개를 등록:

| 이름 | 값 |
|---|---|
| `THREADS_ACCESS_TOKEN` | STEP 4의 장기 토큰 |
| `THREADS_USER_ID` | STEP 5의 id 숫자 |

> 토큰은 절대 코드/문서에 직접 적지 말고 Secrets에만 넣으세요. (한 번 노출되면 폐기하고 재발급)

---

## 테스트 & 운영

### 실제 발행 전 테스트 (DRY RUN)
GitHub 저장소 → **Actions 탭 → Threads Auto-Post → Run workflow** → `dry_run`을 **true**로 실행.
- 실제로 안 올라가고, 어떤 글이 발행될지 로그로만 보여줍니다. 흐름 확인용.

### 실제 첫 발행
1. `queue.yaml`에서 발행할 글의 `approved: false` → **`true`**로 변경(커밋).
   - (또는 나한테 "프롤로그 승인" / "1~3번 승인"이라고 말하면 내가 바꿔줌)
2. 예약 시간(`scheduled_at`)이 지나 있으면, 다음 스케줄 실행 때 자동 발행.
   - 지금 바로 올리고 싶으면 Actions에서 **Run workflow**(dry_run=false) 수동 실행.
3. 발행되면 `state.json`에 기록되고, 같은 글은 다시 안 올라갑니다(중복 방지).

### 발행 규칙
- **1회 실행당 1개**만 발행(폭주 방지).
- `approved: true` + `scheduled_at` 지난 글 중 **가장 이른 것**부터.
- 본문 → (있으면) 첫 댓글 순서로 자동 게시.

### 새 글 추가
`queue.yaml`의 `posts:` 아래에 같은 형식으로 항목을 추가하면 됩니다.
```yaml
  - id: ep9                 # 고유값(중복 금지)
    title: "EP.9 제목"
    scheduled_at: "2026-08-08T21:00:00+09:00"
    approved: false          # 검토 후 true
    body: |
      본문...
    reply: |
      첫 댓글...
```

---

## 운영 팁 / 주의

- **글자 수**: Threads 본문은 최대 500자. 대기열 글은 이 안에 맞춰져 있어요.
- **발행 한도**: Threads API는 24시간에 약 250건 게시 제한(넉넉함).
- **고정(핀)**: `pin: true`인 프롤로그는 발행 후 **앱에서 수동으로 프로필 상단 고정**하세요(API로는 고정 불가).
- **토큰 만료(60일)**: 만료 전 재발급하거나, 갱신 워크플로를 추가할 수 있어요.
  갱신 엔드포인트: `GET https://graph.threads.net/v1.0/refresh_access_token?grant_type=th_refresh_token&access_token=<현재토큰>`
- **초반엔 완전 자동 X**: 발행 직후 1시간 반응이 중요하니(플레이북 1장), 초반에는 발행 시간에 맞춰 댓글 응대를 직접 해주면 도달이 훨씬 잘 나옵니다.
