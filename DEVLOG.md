# 📓 개발일지 (DEVLOG)

> 이 파일은 **다음 세션에서 작업을 이어가기 위한 인수인계 문서**입니다.
> 마지막 업데이트: 2026-06-28

---

## 0. 다음 세션에서 이어가는 법 ⭐

새 채팅을 열고 아래처럼 말하면 됩니다:

> **"C:\Users\KDH\Desktop\jusik 의 주식 대시보드 프로젝트 이어서 할게. DEVLOG.md 읽고 현재 상태 파악해줘."**

그러면 제가 이 파일을 읽고 현재까지 만든 것/구조/다음 할 일을 파악한 뒤 이어갑니다.

- **🌐 배포된 앱(폰에서 접속)**: https://mmrc9rnonvagiez8hqkwku.streamlit.app/ (Streamlit 로그인 후 열람)
- **📦 깃허브 저장소**: https://github.com/kimdike/jusik (Public · `main` 브랜치, `app.py` 진입점)
  - 코드 수정 후 `git push` 하면 Streamlit Cloud가 자동 재배포함
- **대시보드 켜기(로컬)**: "대시보드 켜줘" → `http://localhost:8501`
- **직접 켜기**: PowerShell에서 `cd C:\Users\KDH\Desktop\jusik` → `.venv\Scripts\streamlit run app.py`
- 바로 다음에 할 만한 것 → 아래 **6. 다음 할 일** 참고

---

## 1. 프로젝트 한 줄 요약

한국주식 + 미국주식 + 코인을 한 곳에서 보는 **개인용 투자 보조 대시보드**.
기술적 지표를 종합해 **현재 위치·전문가 목표가 괴리·뉴스**를 초보자도 5초에 이해하도록 정리.
**예측기 아님 / 매수·매도 권유 아님 / 투자 책임 본인.**

## 2. 기술 스택 · 데이터 (전부 무료, API키 불필요)

- **Python 3.14 + Streamlit** (UI), **Plotly** (차트), **pandas/numpy** (계산)
- 주식 시세/펀더멘털/전문가의견: **yfinance** (Yahoo)
- 코인 시세: **업비트** 공개 API
- 종목 검색: **KRX 상장사 목록**(한글명) + Yahoo 검색 + 업비트 + 미국주식 한글 별칭
- 뉴스: **Google News RSS**
- 코인 공포탐욕: **alternative.me**
- 알림: **텔레그램 봇** (토큰은 `~/.claude/channels/telegram/.env`에서 읽음, 깃 미포함)
- 환경: `.venv` (가상환경), 의존성 `requirements.txt` (streamlit, yfinance, pandas, numpy, plotly, requests, lxml)

## 3. 파일 / 모듈 지도

```
jusik/
├─ app.py                 # 대시보드 UI 전체 (7개 화면 + CSS + 카드 컴포넌트)
├─ alerts_run.py          # 알림 러너 (1회/--loop/--test)
├─ requirements-alerts.txt # 알림 전용 경량 의존성 (Actions용; streamlit/plotly 제외)
├─ .github/workflows/alerts.yml    # ⭐ 자동 알림: 30분 크론 → 텔레그램 (차트+가격정리+뉴스)
├─ .github/workflows/briefing.yml  # 🌅 아침 브리핑: KST 평일 08시 워치리스트 요약 발송
├─ .github/workflows/discovery.yml # 🔎 종목 발굴: 매일 밤 스캔→discovery.json 커밋(contents:write)
├─ .github/workflows/market_wrap.yml # 🇰🇷 오늘의 증시 하루정리: KST 평일 15:40 발송(지수·대형주·관전포인트)
├─ .streamlit/config.toml # 테마 팔레트(#F6F8FB 배경, #2563EB 강조)
├─ src/
│  ├─ prices.py     # 시세·환율·펀더멘털(get_fundamentals)·전문가의견·get_quote(거래대금/시총)
│  ├─ indicators.py # 지표 계산 (SMA/EMA/RSI/MACD/볼린저/스토캐스틱/일목/피보나치/ADX/추세선)
│  ├─ signals.py    # 지표 투표→5단계 종합 점수(up_pct), counts, level_label
│  ├─ backtest.py   # 백테스트: 신호 전략 + 눌림목(매수자리) 전략, 룩어헤드 방지, MDD/CAGR/승률
│  ├─ discovery.py  # 종목 발굴 스크리너: 가치점수+조합필터, universe→discovery.json
│  ├─ levels.py     # 지지/저항 가격대 산출(지표 기반)
│  ├─ levels_touch.py # 터치 기반 지지/저항(피벗 클러스터·터치횟수) + 로그회귀 평행채널·채널위치%
│  ├─ summary.py    # 결론3카드(verdict_cards)·컨센서스괴리(consensus_view)·진입(entry_view)·3단총평·별점·긍부정분리
│  ├─ glossary.py   # 지표 설명·근거 해설 사전
│  ├─ search.py     # 이름 검색 (KRX/Yahoo/업비트/미국한글별칭)
│  ├─ news.py       # Google News RSS + 분위기 요약(summarize_news)
│  ├─ market.py     # 시장 개요(지수·공포탐욕·거시뉴스)
│  ├─ notify.py     # 텔레그램 발송 (send=텍스트 / send_photo=이미지+캡션, 토큰 안전 해석)
│  ├─ gitstore.py   # GitHub Contents API로 설정 파일 커밋(클라우드 영구저장) — 알림설정 저장에 사용
│  ├─ chartimg.py   # 차트 PNG 생성(matplotlib) — 지지/저항/목표가 선 + 근거 라벨. 알림 첨부/텔레그램용
│  └─ alerts.py     # 알림 엔진 (신호변화/목표가/손절가, 상태저장) + 종목별 차트 첨부(_send_with_chart)
├─ data/
│  ├─ portfolio.json   # 보유종목   (UI에서 편집/저장)
│  ├─ watchlist.json   # 관심종목
│  ├─ alerts.json      # 알림 설정
│  ├─ alert_state.json # 알림 런타임 상태 (gitignore)
│  ├─ universe.json    # 발굴 스캔 대상(KR 종목명+US 티커, 편집 가능)
│  ├─ discovery.json   # 발굴 스캔 결과 (크론이 자동 갱신/커밋)
│  └─ kr_listing.json  # KRX 목록 캐시 (gitignore, 자동 생성)
└─ 문서: README.md · DEPLOY.md · ALERTS.md · DESIGN.md · stock_dashboard_design.md · DEVLOG.md
```

## 4. 화면(메뉴) 10개 (사이드바 라디오 9 + 가이드 버튼)

1. **📊 기술적 분석** (핵심, 2026-07 UX 개편: 결론먼저·중복제거·스크롤축소) — 검색 → 타임프레임(일/주/월봉) → **Hero(현재가·등락률 + 종합의견 매수/관망/매도 + 종합점수·신뢰도)** → **판단근거 ✅/❌** → 차트(이동평균·일목 + 터치기반 지지/저항 + 평행채널+위치% + 200주선) → **지지·저항 세로 사다리** → 오늘 뉴스 → 접이식(지표별 신호·종합총평·기업지표·전문가컨센서스·피보나치). summary.hero_verdict(). 색상: 상승 초록/중립 노랑/하락 빨강.
2. **🔭 스캐너** — 워치리스트+보유종목 종합신호 일괄 계산 → 강한 순 랭킹. 필터(상승/하락 우세, 강한신호만), RSI/추세/저항거리 컬럼.
3. **🔎 발굴** — 유니버스(주요 KR+US) 매일 밤 스캔 → 가치(저PER·저PBR·배당·52주저점)+조합(우상향 속 눌림목) 매수후보 랭킹. discovery.json 읽어 표시.
4. **🧪 백테스트** — 신호 전략 / 눌림목(매수자리) 전략 검증. 전략 vs 그냥보유 자산곡선 + 거래횟수/승률/MDD/CAGR.
5. **⚖️ 비교** — 관심·보유 종목 2~4개 신호·수익률·지표·정규화 차트 나란히 비교.
6. **🌡️ 시장 개요** — 주요 지수·환율·VIX 등락률 + 코인 공포탐욕 + 거시 뉴스
7. **💰 내 자산** — 보유종목 수익률·자산비중(원화 환산)
8. **⭐ 워치리스트** — 이름 검색 추가/삭제(폰 영구저장) + 신호 모아보기
9. **🔔 알림 설정** — 신호변화/목표가/매수자리/손절가 텔레그램 알림(현재가+버튼), 테스트·수동점검
10. **📖 사용 가이드** — 사이드바 버튼으로 진입, 사용법·메뉴·용어 설명

## 5. 개발 히스토리 (커밋 요약)

- v1: 대시보드 기본(분석/자산/워치리스트) + 지표 종합 신호
- 지표 설명 툴팁/펼침 → 신호 5단계 세분화
- 지지/저항 + 텔레그램 알림(신호변화/목표가/손절가)
- 차트 조작 개선(휠줌/기간버튼/더블클릭 리셋)
- v3: 이름검색 + 종목뉴스 + 시장개요 + 펀더멘털 (코드리뷰 후 XSS·캐시 보강)
- 디자인 2회 개편: Coinbase톤 → **금융 대시보드톤**(stock_dashboard_design.md 기준)
- 전문가 의견 + 검색결과 거래대금/시총
- **총평/컨센서스 개선**: 괴리율 중심 + 추세/모멘텀/진입리스크 3단
- **기술적 분석 UX 개편**: "결론 먼저"(초보자 브리핑) + 긍정/부정 요약 + 중요도 별점
- 종합 신호 점수 설명 추가
- **사용 가이드 페이지** 추가
- **백테스트 페이지** 추가 — 신호 기반 롱전략 워크포워드 검증(룩어헤드 방지), 전략 vs 보유 비교
- **스캐너 페이지** 추가 — 워치리스트+보유 종합신호 랭킹

## 6. 다음 할 일 (로드맵 / 미구현)

우선순위 높음:
- [x] **클라우드 배포** ✅ 2026-06-28 — Streamlit Cloud 배포 완료 (https://mmrc9rnonvagiez8hqkwku.streamlit.app/). 깃허브 Public 저장소 kimdike/jusik. 보유종목(portfolio.json)은 로컬 전용(gitignore)이라 클라우드는 빈 상태로 시작. 알림 자동화는 토큰 미설정 상태(원하면 Streamlit Secrets로).
- [x] **자동 알림(클라우드)** ✅ 2026-06-28 — GitHub Actions 30분 크론으로 PC 꺼도 텔레그램 발송. 신호변화는 워치리스트 전체 자동, 목표가/손절가는 data/alerts.json 설정 필요(로컬 대시보드 알림설정 → 저장 → git push, 또는 직접 편집). Secrets: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID. 상태는 actions/cache. 크론은 UTC 기준이며 60일 무활동 시 비활성화될 수 있음(아무 커밋이나 하면 재개).
- [x] **백테스트** — "이 신호대로 매매했으면 수익률?" 과거 검증 (신호 신뢰도) ✅ 2026-06-28

그 외 아이디어:
- [x] 종목 스캐너 — 관심종목 신호 강한 순 자동 정렬/랭킹 ✅ 2026-06-28
- [ ] 분봉/주봉 등 타임프레임 선택
- [ ] 차트 보조지표 토글(거래량 등), 다크모드
- [ ] 뉴스 감성분석 고도화(현재는 제목 키워드 기반 간이 추정)
- [ ] 종목 비교 화면

## 7. 알아둘 점 / 주의

- **폰에서 목표가 편집**: 알림설정 페이지 저장 시 `data/alerts.json`을 GitHub에 커밋(gitstore). Streamlit Secrets에 `GH_TOKEN`(jusik repo Contents read/write 세밀권한 PAT) 필요. 토큰 있으면 "☁️ 클라우드 저장 연결됨" 표시, 저장 시 자동 알림에 반영(앱 잠시 재배포). 토큰 없으면 로컬 저장만.
- **알림 메시지(간결형, 2026-07)**: 결론 먼저(🟢매수/🟡관망/🔴매도 + 점수) → 💰가격 요약 표(현재/지지/저항/목표/매수/손절, 아이콘+거리%) → 신호변화 시 📰뉴스 1줄. _alert_caption/_price_rows/_opinion. 상세는 대시보드.
- **하루 정리(build_market_wrap)**: '오늘의 증시' — 지수(코스피·코스닥·환율)→대형주 등락→관전포인트. KST 평일 15:40 크론(market_wrap.yml). 수급 데이터는 무료 소스 부재로 제외.
- **알림 종류**: 신호변화 / 🎯목표가(이상) / 🟢매수자리=진입가(이하) / 🛑손절가(이하). alerts.json 키: target/entry/stop/signal_alert. 대시보드 알림설정에서 종목별 입력+버튼(현재가대비 %)으로 설정, 저장 시 GitHub 반영.
- **알림 차트 첨부**: 알림 발생 시 그 종목 차트(chartimg)를 만들어 notify.send_photo로 캡션과 함께 발송(_send_with_chart), 실패 시 텍스트 폴백. 차트엔 사용자 목표가(초록)·매수자리(청록) 선도 표시. 리눅스 러너 한글은 alerts.yml에서 fonts-nanum 설치(chartimg가 NanumGothic 경로 fallback).
- **모바일 반응형**: CUSTOM_CSS에 @media(max-width:640px) — st.columns 세로 정렬, 카드값 nowrap, 표 가로스크롤(.table-scroll). 차트는 범례 하단 이동+부가트레이스 범례숨김+dragmode=pan+responsive.
- **배포 운영**: 코드 수정 후 `git push` → Streamlit Cloud 자동 재배포(2~3분). 단 `data/portfolio.json`은 gitignore라 푸시 안 됨(로컬 전용). 앱 뷰어 인증 ON 상태(로그인해야 열람) — 변경은 Streamlit Manage app → Settings → Sharing.
- **실행 전제**: 자동 알림(알림 설정)은 PC가 켜져 있거나 클라우드 배포 시에만 작동. 현재는 로컬.
- **데이터 환경 특이사항**: 이 환경의 시세는 실제와 다를 수 있음(예: 삼성전자 35만원대, 코스피 9000선). 로직은 정상.
- **Windows 콘솔 한글**: 테스트 스크립트는 `PYTHONIOENCODING=utf-8` 필요(cp949 깨짐). 브라우저는 무관.
- **Streamlit 재시작 필요**: `.streamlit/config.toml`(테마) 변경 시 서버 재시작 필요. `app.py` 코드 변경은 새로고침으로 반영.
- **시크릿**: 텔레그램 토큰은 절대 커밋 안 함(.gitignore: config/notify.json, alert_state.json, kr_listing.json).
- **검증 방식**: 헤드리스 Streamlit(포트 8766~8768) 띄워 Playwright로 스크린샷 확인 후 커밋하는 흐름 사용.
