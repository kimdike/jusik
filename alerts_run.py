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
import json
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
    ap.add_argument("--brief", nargs="?", const="pre", choices=["pre", "open", "hourly"],
                    help="브리핑 발송: pre(장 전 08:30) / open(장 시작 30분) / hourly(정시 점검)")
    ap.add_argument("--group-brief", action="store_true",
                    help="단톡방 종목 브리핑 발송 (차트+가격요약+매수구간+뉴스)")
    ap.add_argument("--group-summary", action="store_true",
                    help="단톡방 종목 텍스트 요약 1통 (차트 없음)")
    ap.add_argument("--spike", action="store_true",
                    help="단톡방 종목 급등/급락 감지 후 해당 종목만 알림")
    ap.add_argument("--wrap-group", action="store_true",
                    help="--wrap 을 개인방+단톡방 양쪽에 발송")
    ap.add_argument("--add", metavar="NAME", help="워치리스트에 종목 추가 (이름/티커로 검색)")
    ap.add_argument("--market", metavar="KR|US|COIN", help="--add 시 시장 지정")
    ap.add_argument("--remove", metavar="NAME", help="워치리스트에서 종목 제거")
    ap.add_argument("--list", action="store_true", help="현재 워치리스트 보기")
    ap.add_argument("--discover", action="store_true", help="종목 발굴 스캔 → discovery.json 저장")
    ap.add_argument("--wrap", action="store_true", help="오늘의 증시 하루 정리 발송")
    ap.add_argument("--halt", action="store_true", help="사이드카/서킷브레이커 발동 점검(뉴스 속보)")
    args = ap.parse_args()

    if args.halt:
        msgs = alerts.check_market_halt(send_telegram=True)
        if msgs:
            print(f"[{_ts()}] 시장 중단 알림 {len(msgs)}건 발송:")
            for m in msgs:
                print("  -", m.replace("\n", " / "))
        else:
            print(f"[{_ts()}] 사이드카/CB 발동 없음")
        return

    if args.test:
        ok, info = notify.send("🔔 [테스트] 주식 대시보드 알림이 정상 연결됐어요!")
        print("테스트 발송:", "성공 ✅" if ok else f"실패 ❌ ({info})")
        return

    if args.list or args.add or args.remove:
        if args.add:
            r = alerts.add_watch(args.add, market=args.market)
            print(("✅ " if r["ok"] else "⚠️ ") + r["msg"])
            if not r["ok"] and r["candidates"]:
                print("후보:", ", ".join(f"{c['name']}({c['symbol']}/{c['market']})"
                                        for c in r["candidates"][:5]))
        if args.remove:
            r = alerts.remove_watch(args.remove)
            print(("✅ " if r["ok"] else "⚠️ ") + r["msg"])
        wl = json.loads(alerts.WATCHLIST_FILE.read_text(encoding="utf-8"))
        print(f"\n현재 워치리스트 {len(wl)}종목:")
        for w in wl:
            print(f"  • {w['name']} ({w['symbol']}/{w['market']})")
        return

    if args.group_brief:
        log = alerts.build_group_briefing(send_telegram=True)
        print(f"[{_ts()}] 단톡방 브리핑:")
        for line in log:
            print("  -", line)
        return

    if args.group_summary:
        text = alerts.build_group_summary(send_telegram=True, kind="open")
        print(f"[{_ts()}] 단톡방 요약:")
        print(text)
        return

    if args.spike:
        log = alerts.check_spikes(send_telegram=True)
        print(f"[{_ts()}] 급변동 점검:")
        for line in log:
            print("  -", line)
        return

    if args.brief:
        text = alerts.build_briefing(send_telegram=True, kind=args.brief)
        print(f"[{_ts()}] 브리핑({args.brief}) 발송:")
        print(text)
        return

    if args.wrap:
        tg = ["personal", "group"] if args.wrap_group else ["personal"]
        text = alerts.build_market_wrap(send_telegram=True, targets=tg)
        print(f"[{_ts()}] 하루 정리 발송:")
        print(text)
        return

    if args.discover:
        from src import discovery
        r = discovery.run_and_save(timestamp=_ts())
        combo = sum(1 for c in r["candidates"] if c.get("combo"))
        print(f"[{_ts()}] 발굴 스캔: 후보 {len(r['candidates'])}/{r['scanned']} (매수자리 {combo}) · 실패 {r['failed']}")
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
