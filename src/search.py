"""
종목 이름 검색.

  - 주식: Yahoo Finance search API (이름/티커 → 후보)
      예) "삼성", "samsung", "apple", "엔비디아"
      .KS/.KQ → 한국(KR, 6자리코드), 그 외 → 미국(US)
  - 코인: 업비트 마켓 목록(한글명 매칭)
      예) "비트코인", "btc", "이더"

반환: [{"name", "symbol", "market", "extra"}]
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 8
_YH_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
_UPBIT_ALL = "https://api.upbit.com/v1/market/all"
_KRX_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
_KR_FILE = Path(__file__).resolve().parent.parent / "data" / "kr_listing.json"

_upbit_cache: list[dict] | None = None
_kr_cache: list[dict] | None = None

# 인기 미국주식 한글 별칭 (한글로 쳐도 검색되게)
_US_ALIASES = {
    "테슬라": ("TSLA", "Tesla"), "애플": ("AAPL", "Apple"),
    "엔비디아": ("NVDA", "NVIDIA"), "구글": ("GOOGL", "Alphabet"),
    "알파벳": ("GOOGL", "Alphabet"), "아마존": ("AMZN", "Amazon"),
    "마이크로소프트": ("MSFT", "Microsoft"), "엠에스": ("MSFT", "Microsoft"),
    "메타": ("META", "Meta"), "페이스북": ("META", "Meta"),
    "넷플릭스": ("NFLX", "Netflix"), "팔란티어": ("PLTR", "Palantir"),
    "코인베이스": ("COIN", "Coinbase"), "AMD": ("AMD", "AMD"),
    "인텔": ("INTC", "Intel"), "마이크론": ("MU", "Micron"),
    "브로드컴": ("AVGO", "Broadcom"), "퀄컴": ("QCOM", "Qualcomm"),
}


def _search_us_alias(query: str) -> list[dict]:
    q = query.strip().lower()
    out = []
    for kor, (tk, eng) in _US_ALIASES.items():
        if q and (q in kor.lower() or q == tk.lower()):
            out.append({"name": f"{eng} ({kor})", "symbol": tk, "market": "US", "extra": "미국주식"})
    return out


def _kr_catalog() -> list[dict]:
    """KRX 상장사 목록 [{name, code}] (한글명 검색용). 파일 캐시 후 재사용."""
    global _kr_cache
    if _kr_cache is not None:
        return _kr_cache
    if _KR_FILE.exists():
        try:
            _kr_cache = json.loads(_KR_FILE.read_text(encoding="utf-8"))
            return _kr_cache
        except Exception:
            pass
    try:
        import pandas as pd
        r = requests.get(_KRX_URL, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        df = pd.read_html(io.BytesIO(r.content), encoding="euc-kr")[0][["회사명", "종목코드"]]
        df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
        _kr_cache = [
            {"name": str(n), "code": str(c)}
            for n, c in zip(df["회사명"], df["종목코드"])
            if str(c).isdigit()  # yfinance 호환되는 순수 숫자코드만
        ]
        # 정상 파싱(비어있지 않음)일 때만 파일 캐시에 저장 (오류 응답으로 캐시 오염 방지)
        if _kr_cache:
            _KR_FILE.parent.mkdir(parents=True, exist_ok=True)
            _KR_FILE.write_text(json.dumps(_kr_cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        _kr_cache = []
    return _kr_cache


def _search_kr(query: str, limit: int) -> list[dict]:
    q = query.strip().lower()
    matches = []
    for item in _kr_catalog():
        name = str(item.get("name", ""))
        code = str(item.get("code", ""))
        if not name or not code:
            continue
        nl = name.lower()
        if q in nl or q == code:
            # 랭킹: 정확일치(0) < 접두일치(1) < 부분일치(2), 동일 등급은 이름 짧은 순
            rank = 0 if nl == q else (1 if nl.startswith(q) else 2)
            matches.append((rank, len(name), name, code))
    matches.sort(key=lambda x: (x[0], x[1]))
    return [
        {"name": n, "symbol": c, "market": "KR", "extra": "한국주식"}
        for _, _, n, c in matches[:limit]
    ]


def _upbit_catalog() -> list[dict]:
    global _upbit_cache
    if _upbit_cache is None:
        try:
            data = requests.get(_UPBIT_ALL, params={"isDetails": "false"},
                                timeout=_TIMEOUT).json()
            _upbit_cache = [m for m in data if str(m.get("market", "")).startswith("KRW-")]
        except Exception:
            _upbit_cache = []
    return _upbit_cache


def _search_coins(query: str, limit: int) -> list[dict]:
    q = query.strip().lower()
    out = []
    for m in _upbit_catalog():
        sym = m["market"].split("-", 1)[1]  # KRW-BTC -> BTC
        kor = str(m.get("korean_name", ""))
        eng = str(m.get("english_name", ""))
        if q in kor.lower() or q in eng.lower() or q in sym.lower():
            out.append({"name": kor or sym, "symbol": sym, "market": "COIN", "extra": "업비트"})
        if len(out) >= limit:
            break
    return out


def _search_stocks(query: str, limit: int) -> list[dict]:
    try:
        r = requests.get(
            _YH_SEARCH,
            params={"q": query, "quotesCount": limit, "newsCount": 0, "lang": "ko-KR"},
            headers=_HEADERS, timeout=_TIMEOUT,
        ).json()
    except Exception:
        return []
    out = []
    for q in r.get("quotes", []):
        qt = q.get("quoteType")
        sym = q.get("symbol", "")
        if qt not in ("EQUITY", "ETF") or not sym:
            continue
        name = q.get("shortname") or q.get("longname") or sym
        exch = (q.get("exchange") or "")
        if sym.endswith((".KS", ".KQ")):
            out.append({"name": name, "symbol": sym.split(".")[0], "market": "KR",
                        "extra": "코스피" if sym.endswith(".KS") else "코스닥"})
        elif "." not in sym:  # 미국 등 (접미사 없는 티커)
            out.append({"name": name, "symbol": sym, "market": "US", "extra": exch or "US"})
    return out[:limit]


def search_symbols(query: str, limit: int = 8) -> list[dict]:
    """이름/티커로 종목 검색. 주식+코인 통합 결과."""
    query = (query or "").strip()
    if not query:
        return []
    kr = _search_kr(query, limit)          # 한글 종목명 (KRX 목록)
    coins = _search_coins(query, limit)    # 코인 (업비트 한글명)
    alias = _search_us_alias(query)        # 미국주식 한글 별칭
    stocks = _search_stocks(query, limit)  # 미국 등 (Yahoo)
    # 한국→코인→미국별칭→미국(Yahoo) 순, 중복 제거
    seen, merged = set(), []
    for item in kr + coins + alias + stocks:
        key = (item["symbol"], item["market"])
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged[:limit]
