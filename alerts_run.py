"""
알림 러너 — 신호 변화 + 목표가/손절가 점검 후 텔레그램 발송.

사용법 (PowerShell, 프로젝트 폴더에서):
  .venv\\Scripts\\python alerts_run.py            # 1회 점검
  .venv\\Scripts\\python alerts_run.py --loop 15  # 15분마다 반복
  .venv\\Scripts\\python alerts_run.py --test     # 테스트 메시지 1통

자동 실행은 Windows 작업 스케줄러로 위 '1회 점검'을 주기 등록하면 됩니다 (DEPLOY/ALERTS 안내 참고).
"""
from __future__ import annotations

import argparse
import sys
import time

# Windows 콘솔 한글 출력 안전화
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src import alerts, notify


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_once() -> None:
    msgs = alerts.run_once(send_telegram=True)
    if msgs:
        print(f"[{_ts()}] 알림 {len(msgs)}건 발송:")
        for m in msgs:
            print("  -", m.replace("\n", " / "))
    else:
        print(f"[{_ts()}] 변화 없음 (알림 없음)")


def main() -> None:
    ap = argparse.ArgumentParser(description="주식 알림 러너")
    ap.add_argument("--loop", type=int, metavar="MIN", help="N분마다 반복 실행")
    ap.add_argument("--test", action="store_true", help="텔레그램 테스트 메시지 발송")
    args = ap.parse_args()

    if args.test:
        ok, info = notify.send("🔔 [테스트] 주식 대시보드 알림이 정상 연결됐어요!")
        print("테스트 발송:", "성공 ✅" if ok else f"실패 ❌ ({info})")
        return

    if not notify.is_configured():
        print("⚠️ 텔레그램 토큰/chat_id 미설정 — 알림은 건너뜁니다.")

    if args.loop:
        print(f"[{_ts()}] 반복 모드 시작 — {args.loop}분 간격. 종료: Ctrl+C")
        try:
            while True:
                run_once()
                time.sleep(args.loop * 60)
        except KeyboardInterrupt:
            print("\n중지됨.")
    else:
        run_once()


if __name__ == "__main__":
    main()
