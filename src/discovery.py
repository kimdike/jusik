"""
종목 발굴(스크리너) 엔진.

가치(저PER·저PBR·배당·52주 저점권) + 조합 타이밍(장기 우상향 + 단기 눌림목)으로
매수 후보를 점수화해 추린다. 펀더멘털 조회가 느려 GitHub Actions에서 주기적으로
스캔해 data/discovery.json 에 저장하고, 대시보드는 그 결과를 즉시 표시한다.

주의: 투자 권유가 아니라 '후보 탐색' 보조 도구. 수치는 참고용.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import indicators as ind
from . import prices, search, signals

_DATA = Path(__file__).resolve().parent.parent / "data"
UNIVERSE_FILE = _DATA / "universe.json"
DISCOVERY_FILE = _DATA / "discovery.json"


def _last(all_ind: dict, key: str):
    s = all_ind.get(key)
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def value_score(per, pbr, div, pos) -> int:
    """저평가 점수 0~100 (낮은 PER/PBR, 높은 배당, 낮은 52주 위치일수록 높음)."""
    vs = 0
    if per and per > 0:
        vs += 25 if per < 10 else 15 if per < 15 else 7 if per < 25 else 0
    if pbr and pbr > 0:
        vs += 25 if pbr < 1 else 15 if pbr < 1.5 else 7 if pbr < 2.5 else 0
    if div:
        vs += 20 if div >= 3 else 10 if div >= 1.5 else 3
    if pos is not None:
        vs += 30 if pos < 0.3 else 18 if pos < 0.5 else 7 if pos < 0.7 else 0
    return vs


def screen_one(name: str, sym: str, mkt: str) -> dict | None:
    """단일 종목 스크리닝. 데이터 부족/실패 시 None."""
    df = prices.get_ohlcv(sym, mkt, "1y")
    if df is None or len(df) < 130:
        return None
    fund = prices.get_fundamentals(sym, mkt) or {}
    all_ind = ind.compute_all(df)
    res = signals.evaluate(df)
    cur = float(df["close"].iloc[-1])
    sma20, sma60, sma120 = _last(all_ind, "sma20"), _last(all_ind, "sma60"), _last(all_ind, "sma120")
    rsi = _last(all_ind, "rsi")
    per, pbr = fund.get("per"), fund.get("pbr")
    div, pos = fund.get("dividend_yield"), fund.get("week52_pos")

    vs = value_score(per, pbr, div, pos)
    uptrend = sma120 is not None and cur > sma120        # 장기 추세 우상향
    pullback = (sma20 is not None and sma60 is not None   # 단기 눌림목(추세 내 조정)
                and cur < sma20 and cur > sma60 * 0.96
                and (rsi is None or 35 <= rsi <= 58))
    combo = bool(uptrend and pullback)
    return {
        "name": name, "symbol": sym, "market": mkt, "price": cur,
        "per": round(per, 1) if per else None,
        "pbr": round(pbr, 2) if pbr else None,
        "div": round(div, 2) if div else None,
        "week52_pos": round(pos * 100) if pos is not None else None,
        "value_score": vs,
        "up_pct": res.get("up_pct"),
        "rsi": round(rsi) if rsi is not None else None,
        "uptrend": uptrend, "pullback": pullback, "combo": combo,
    }


def _resolve_universe() -> list[tuple[str, str, str]]:
    """universe.json → [(name, symbol, market)]. KR은 종목명을 KRX 목록의 코드로 변환."""
    try:
        uni = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[tuple[str, str, str]] = []
    catalog = {str(c.get("name")): str(c.get("code")) for c in search._kr_catalog()}
    for nm in uni.get("kr", []):
        code = catalog.get(nm)
        if code:
            out.append((nm, code, "KR"))
    for tk in uni.get("us", []):
        out.append((tk, tk, "US"))
    return out


def run_discovery(timestamp: str = "", sleep: float = 0.3, min_value: int = 25) -> dict:
    """전체 유니버스 스캔 → 결과 dict. timestamp는 호출부에서 주입(스크립트 시간)."""
    universe = _resolve_universe()
    candidates, scanned, failed = [], 0, 0
    for name, sym, mkt in universe:
        try:
            row = screen_one(name, sym, mkt)
            scanned += 1
            if row and (row["value_score"] >= min_value or row["combo"]):
                candidates.append(row)
        except Exception:
            failed += 1
        if sleep:
            time.sleep(sleep)  # 야후 레이트리밋 완화
    # 정렬: 조합(combo) 통과 우선 → 가치점수 → 신호
    candidates.sort(key=lambda r: (r["combo"], r["value_score"], r.get("up_pct") or 0), reverse=True)
    return {
        "generated": timestamp,
        "universe": len(universe),
        "scanned": scanned,
        "failed": failed,
        "candidates": candidates,
    }


def run_and_save(timestamp: str = "", sleep: float = 0.3) -> dict:
    result = run_discovery(timestamp=timestamp, sleep=sleep)
    DISCOVERY_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
