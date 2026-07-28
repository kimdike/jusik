# 외부 스케줄러 (Cloudflare Workers)

## 왜 옮기나

GitHub Actions 의 `schedule:` 크론은 무료 러너에서 **best-effort** 라 부하가 걸리면
조용히 건너뛴다. 실패가 아니라 아예 실행되지 않으므로 로그에도 안 남는다.

실측 (2026-07-27, `alerts.yml` 은 `*/5` 설정):

```
00:12 → 04:04   (3시간 52분 공백)
04:04 → 07:46   (3시간 42분)
07:46 → 10:57   (3시간 11분)
10:57 → 13:41   (2시간 44분)
```

5분 간격이어야 할 알림이 1~4시간에 한 번 돌았다. "신호 바뀌면 즉시" 가 성립하지 않는다.

반면 **`workflow_dispatch` 는 API 로 호출하면 곧바로 실행된다.** 그래서 시각을 지키는
역할만 Cloudflare 로 옮기고, 실제 실행은 그대로 GitHub Actions 가 맡는다.
파이썬 코드는 하나도 바꾸지 않는다.

```
Cloudflare Cron (5분마다)
        │  무엇을 돌릴 시각인지 판단
        ▼
GitHub API workflow_dispatch
        ▼
기존 워크플로우 그대로 실행 → 텔레그램
```

## 설치 (한 번만)

### 1. GitHub 토큰 발급

https://github.com/settings/personal-access-tokens/new

- Repository access: `kimdike/jusik` 만 선택
- Permissions → Repository permissions → **Actions: Read and write**
- 만료일은 길게 (만료되면 알림이 조용히 멈춘다)

발급된 `github_pat_...` 토큰을 복사해둔다.

### 2. Cloudflare 배포

```bash
npm install -g wrangler
cd deploy/cloudflare-worker

wrangler login                 # 브라우저에서 Cloudflare 로그인
wrangler secret put GH_TOKEN   # 위에서 복사한 토큰 붙여넣기
wrangler deploy
```

배포되면 `https://jusik-scheduler.<계정>.workers.dev` 주소가 나온다.
브라우저로 열면 현재 스케줄이 보이고, `?run=alerts.yml` 을 붙이면 즉시 실행된다.

### 3. GitHub 쪽 크론 정리

Cloudflare 가 제대로 도는 걸 며칠 확인한 뒤, 각 워크플로우의 `schedule:` 블록을
지우면 된다. 그 전까지는 둘 다 돌아도 문제없다 —
`concurrency` 설정이 겹침을 막고, 알림은 상태 기반이라 중복 발송되지 않는다.

## 스케줄 바꾸기

`worker.js` 의 `SCHEDULE` 배열만 고치고 `wrangler deploy` 하면 된다.
시각은 전부 **UTC** 기준이다 (KST = UTC + 9).

| 워크플로우 | 주기 | KST |
|---|---|---|
| `alerts.yml` | 10분마다 | 24시간 |
| `halt.yml` | 5분마다 | 평일 09~15시 |
| `hourly.yml` | 매시 정각 | 평일 10~15시, 23~06시 |
| `briefing.yml` (pre) | 1일 1회 | 평일 08:30 |
| `briefing.yml` (open) | 1일 1회 | 평일 09:30 |
| `market_wrap.yml` | 1일 1회 | 평일 16:00 |

## 비용

Cloudflare Workers 무료 플랜: 하루 10만 요청. 5분마다 = 하루 288회라 여유롭다.

## 문제가 생기면

```bash
wrangler tail          # 실시간 로그 (dispatch 성공/실패가 찍힘)
```

- `401` → 토큰 만료 또는 권한 부족 (Actions: Read and write 확인)
- `404` → 워크플로우 파일명 오타, 또는 해당 워크플로우에 `workflow_dispatch:` 가 없음
- 아무것도 안 찍힘 → `wrangler deploy` 가 실제로 됐는지, 크론이 등록됐는지 대시보드에서 확인
