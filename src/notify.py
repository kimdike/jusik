"""
텔레그램 알림 전송.

봇 토큰/채팅ID 해석 우선순위 (토큰은 코드/깃에 절대 저장하지 않음):
  1) 환경변수 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
  2) 프로젝트 로컬 config/notify.json  (gitignore 됨)
  3) Claude Code 텔레그램 플러그인 설정
     ~/.claude/channels/telegram/.env        (토큰)
     ~/.claude/channels/telegram/access.json (chat_id = allowFrom[0])
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

_PROJECT = Path(__file__).resolve().parent.parent
_LOCAL_CONF = _PROJECT / "config" / "notify.json"
_PLUGIN_DIR = Path.home() / ".claude" / "channels" / "telegram"


def _read_local_conf() -> dict:
    try:
        return json.loads(_LOCAL_CONF.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_plugin_env_token() -> str | None:
    try:
        for line in (_PLUGIN_DIR / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _read_plugin_chat_id() -> str | None:
    try:
        data = json.loads((_PLUGIN_DIR / "access.json").read_text(encoding="utf-8"))
        allow = data.get("allowFrom") or []
        if allow:
            return str(allow[0])
    except Exception:
        pass
    return None


def resolve_token() -> str | None:
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN")
        or _read_local_conf().get("telegram_token")
        or _read_plugin_env_token()
    )


def resolve_chat_id() -> str | None:
    return (
        os.environ.get("TELEGRAM_CHAT_ID")
        or str(_read_local_conf().get("chat_id") or "") or None
        or _read_plugin_chat_id()
    )


def resolve_group_token() -> str | None:
    """그룹(단톡)방 봇 토큰. 없으면 개인 봇 토큰으로 폴백."""
    conf = _read_local_conf()
    return (
        os.environ.get("TELEGRAM_GROUP_BOT_TOKEN")
        or conf.get("group_telegram_token")
        or resolve_token()
    )


def resolve_group_chat_id() -> str | None:
    """그룹(단톡)방 chat_id. 개인방으로 폴백하지 않는다 —
    잘못 폴백하면 그룹 알림이 조용히 개인방으로 가서 눈치채기 어렵다."""
    return (
        os.environ.get("TELEGRAM_GROUP_CHAT_ID")
        or str(_read_local_conf().get("group_chat_id") or "") or None
    )


def creds(target: str = "personal") -> tuple[str | None, str | None]:
    """발송 대상별 (토큰, chat_id). target: 'personal' | 'group'."""
    if str(target).lower() == "group":
        return resolve_group_token(), resolve_group_chat_id()
    return resolve_token(), resolve_chat_id()


_MAX_RETRY = 3          # 429 재시도 횟수
_RETRY_CAP = 60         # retry_after 가 이보다 크면 포기 (무한 대기 방지)


def _post(url: str, *, retries: int = _MAX_RETRY, **kwargs) -> tuple[bool, str]:
    """텔레그램 API 호출 + 429(속도 제한) 재시도.

    그룹 채팅은 분당 약 20통 제한이 있어, 종목을 연달아 보내면 뒤쪽이 429로 거부된다.
    응답의 retry_after 만큼 기다렸다가 다시 보낸다.
    """
    import time

    last = ""
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, **kwargs)
        except Exception as e:
            return False, f"전송 오류: {e}"
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "전송 성공"
        last = f"전송 실패: {resp.status_code} {resp.text[:200]}"
        if resp.status_code != 429 or attempt == retries:
            return False, last
        try:
            wait = float(resp.json()["parameters"]["retry_after"])
        except Exception:
            wait = 5.0
        if wait > _RETRY_CAP:
            return False, last + f" (retry_after {wait:.0f}s 초과로 포기)"
        time.sleep(wait + 0.5)
    return False, last


def send(text: str, chat_id: str | None = None, token: str | None = None,
         parse_mode: str | None = None) -> tuple[bool, str]:
    """텔레그램 메시지 발송. (성공여부, 메시지) 반환. parse_mode: 'HTML'/'MarkdownV2'."""
    token = token or resolve_token()
    chat_id = chat_id or resolve_chat_id()
    if not token:
        return False, "봇 토큰을 찾을 수 없습니다 (TELEGRAM_BOT_TOKEN 또는 config/notify.json)."
    if not chat_id:
        return False, "chat_id 를 찾을 수 없습니다."
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _post(f"https://api.telegram.org/bot{token}/sendMessage",
                 json=payload, timeout=10)


def send_photo(photo_path: str, caption: str = "",
               chat_id: str | None = None, token: str | None = None,
               parse_mode: str | None = None) -> tuple[bool, str]:
    """이미지 파일을 캡션과 함께 전송 (텔레그램 sendPhoto). (성공여부, 메시지). parse_mode: 'HTML' 등."""
    token = token or resolve_token()
    chat_id = chat_id or resolve_chat_id()
    if not token:
        return False, "봇 토큰을 찾을 수 없습니다."
    if not chat_id:
        return False, "chat_id 를 찾을 수 없습니다."
    data = {"chat_id": chat_id, "caption": caption[:1024]}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        # 재시도 시 스트림이 소진되지 않게 바이트로 읽어둔다
        with open(photo_path, "rb") as f:
            blob = f.read()
    except Exception as e:
        return False, f"이미지 읽기 실패: {e}"
    return _post(f"https://api.telegram.org/bot{token}/sendPhoto",
                 data=data, files={"photo": ("chart.png", blob, "image/png")},
                 timeout=30)


def is_configured() -> bool:
    return bool(resolve_token() and resolve_chat_id())
