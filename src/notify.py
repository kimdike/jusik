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


def send(text: str, chat_id: str | None = None, token: str | None = None,
         parse_mode: str | None = None) -> tuple[bool, str]:
    """텔레그램 메시지 발송. (성공여부, 메시지) 반환. parse_mode: 'HTML'/'MarkdownV2'."""
    token = token or resolve_token()
    chat_id = chat_id or resolve_chat_id()
    if not token:
        return False, "봇 토큰을 찾을 수 없습니다 (TELEGRAM_BOT_TOKEN 또는 config/notify.json)."
    if not chat_id:
        return False, "chat_id 를 찾을 수 없습니다."
    try:
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "전송 성공"
        return False, f"전송 실패: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return False, f"전송 오류: {e}"


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
    try:
        data = {"chat_id": chat_id, "caption": caption[:1024]}
        if parse_mode:
            data["parse_mode"] = parse_mode
        with open(photo_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data=data,
                files={"photo": f},
                timeout=30,
            )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "전송 성공"
        return False, f"전송 실패: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return False, f"전송 오류: {e}"


def is_configured() -> bool:
    return bool(resolve_token() and resolve_chat_id())
