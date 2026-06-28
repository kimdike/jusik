# ☁️ 모바일에서 보기 — Streamlit 클라우드 배포 가이드

목표: 깃허브에 코드 올리고 → Streamlit 무료 클라우드에 배포 →
**PC를 꺼도 폰에서 항상 접속되는 영구 주소** 만들기.

> 현재 상태: 코드는 이미 git 커밋 완료 (배포 준비 끝). 남은 건 깃허브 업로드 + 배포뿐.

---

## 준비물 (둘 다 무료, 깃허브 하나로 통합 로그인)
1. **GitHub 계정** — https://github.com (없으면 가입)
2. **Streamlit Community Cloud** — https://share.streamlit.io (깃허브로 로그인)

> ⚠️ 깃허브 로그인 / Streamlit 로그인은 브라우저 인증이라 **본인이 직접** 해야 합니다.
> 나머지(저장소 생성·코드 push)는 Claude가 대신 해드릴 수 있어요.

---

## 방법 A — Claude가 대부분 대신 (추천)
PC 앞에 앉으면 Claude에게 **"PC 앞이야, 배포 진행"** 이라고 말하세요. 순서:

1. Claude가 GitHub CLI(`gh`) 설치
2. KDH님이 터미널에 `! gh auth login` 입력 → 브라우저에서 깃허브 로그인 (1회)
3. Claude가 **비공개 저장소** 생성 + 코드 push (자동)
4. https://share.streamlit.io 접속 → 깃허브로 로그인
5. **"New app"** → 방금 만든 저장소 선택 → Main file: `app.py` → **Deploy**
6. 2~3분 후 `https://...streamlit.app` 주소 완성 → **폰 홈화면에 추가해두면 앱처럼 사용**

---

## 방법 B — 직접 다 하기
1. github.com 에서 **New repository** → 이름 `jusik` → **Private** → Create
2. 안내에 나오는 명령을 PowerShell(이 폴더)에서 실행:
   ```powershell
   git remote add origin https://github.com/<내아이디>/jusik.git
   git branch -M main
   git push -u origin main
   ```
   (첫 push 때 브라우저로 깃허브 로그인 창이 뜸)
3. share.streamlit.io → New app → 저장소 선택 → `app.py` → Deploy

---

## ⚠️ 알아둘 점
- **보유종목 "저장" 기능:** 클라우드는 파일이 재시작 때 초기화돼서, 대시보드에서 종목을
  수정해도 영구 저장되진 않습니다(접속 중에는 유지). 영구 저장이 필요하면 다음 버전에서
  구글시트/DB 연동을 붙이면 됩니다. **기술적 분석·시세 조회는 클라우드에서 완벽 동작.**
- **공개 범위:** 저장소는 Private 권장. 배포된 앱도 Streamlit 설정에서
  "특정 이메일만 보기"로 비공개 전환 가능 (Settings → Sharing).
- **데이터:** yfinance·업비트 모두 클라우드에서도 무료로 잘 불러옵니다.
