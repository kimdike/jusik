"""
종목/키워드 관련 뉴스 (Google News RSS, 무료·키 불필요).

get_news("삼성전자")            -> 한국어 뉴스
get_news("Apple", region="US") -> 영어 뉴스
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone

import requests

# 제목 기반 간이 감성 사전 (정확한 NLP가 아니라 분위기 추정용)
_POS_WORDS = ["상승", "호재", "강세", "신고가", "돌파", "수주", "흑자", "개선", "확대", "성장",
              "기대", "협력", "최대", "급등", "호조", "수혜", "순매수", "상향", "흥행", "역대",
              "반등", "회복", "달성", "선정", "수출", "최고"]
_NEG_WORDS = ["하락", "약세", "급락", "적자", "우려", "리스크", "하향", "경고", "부진", "매도",
              "손실", "감소", "충격", "폭락", "악재", "둔화", "축소", "위기", "논란", "제재",
              "순매도", "철수", "리콜", "소송", "파산", "셧다운"]
_STOP = {"관련", "종목", "증권", "주가", "오늘", "유가증권", "속보", "단독", "공시", "대비",
         "기자", "전일", "이슈", "분석", "전망", "마감", "장중", "시황", "코스피", "코스닥"}

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 8


def _fmt_date(pub: str) -> str:
    """RSS pubDate(RFC822) -> 'MM/DD HH:MM' (실패 시 원문)."""
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(pub, fmt)
            return dt.strftime("%m/%d %H:%M")
        except Exception:
            continue
    return pub[:16] if pub else ""


def get_news(query: str, region: str = "KR", limit: int = 8) -> list[dict]:
    """
    반환: [{"title", "source", "published", "link"}]
    region: "KR"(한국어) / "US"(영어)
    """
    query = (query or "").strip()
    if not query:
        return []
    if region == "US":
        params = "hl=en-US&gl=US&ceid=US:en"
    else:
        params = "hl=ko&gl=KR&ceid=KR:ko"
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&{params}"
    try:
        xml = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT).text
        root = ET.fromstring(xml)
    except Exception:
        return []

    out = []
    for item in root.findall(".//item")[:limit]:
        raw_title = (item.findtext("title") or "").strip()
        # Google News 제목은 "헤드라인 - 언론사" 형태
        if " - " in raw_title:
            headline, source = raw_title.rsplit(" - ", 1)
        else:
            headline, source = raw_title, (item.findtext("source") or "")
        out.append({
            "title": headline.strip(),
            "source": source.strip(),
            "published": _fmt_date(item.findtext("pubDate") or ""),
            "link": (item.findtext("link") or "").strip(),
        })
    return out


def summarize_news(items: list[dict], exclude: str = "") -> dict:
    """제목 기반 분위기 추정 + 주요 키워드. {pos, neu, neg, total, keywords}."""
    # 검색어 자체는 키워드에서 제외 (예: '삼성전자' 검색 시 '삼성전자' 키워드 노이즈 제거)
    ex = {w for w in re.split(r"\s+", exclude.strip()) if w} | {exclude.strip()}
    pos = neu = neg = 0
    cnt: Counter = Counter()
    for n in items:
        t = n.get("title", "")
        p = sum(1 for w in _POS_WORDS if w in t)
        m = sum(1 for w in _NEG_WORDS if w in t)
        if p > m:
            pos += 1
        elif m > p:
            neg += 1
        else:
            neu += 1
        for w in re.split(r"[\s,·…\"'\[\]()|/~!?.\-—]+", t):
            w = w.strip()
            if len(w) >= 2 and not w.isdigit() and w not in _STOP and w not in ex:
                cnt[w] += 1
    keywords = [w for w, c in cnt.most_common(6) if c >= 2][:4]
    return {"pos": pos, "neu": neu, "neg": neg, "total": len(items), "keywords": keywords}
