"""
GitHub 저장소에 파일을 직접 커밋 (클라우드에서 설정을 영구 저장하기 위함).

Streamlit Cloud는 파일이 재시작 때 초기화되므로, 폰/클라우드에서 바꾼 설정
(예: 목표가·손절가 alerts.json)을 GitHub 저장소에 커밋해 영구화한다.
그러면 자동 알림(GitHub Actions)도 같은 파일을 읽어 반영한다.

토큰은 호출부에서 주입한다(코드/깃에 저장하지 않음). Streamlit secrets(GH_TOKEN) 권장.
세밀권한 토큰(해당 저장소 Contents read/write)만 있으면 된다.
"""
from __future__ import annotations

import base64

import requests

_API = "https://api.github.com"
_TIMEOUT = 15


def save_file(
    repo: str,
    path: str,
    content_str: str,
    message: str,
    token: str,
    branch: str = "main",
) -> tuple[bool, str]:
    """
    repo("owner/name")의 path 파일을 content_str 내용으로 생성/갱신(커밋).
    반환: (성공여부, 메시지).
    """
    if not token or not repo:
        return False, "GitHub 토큰/저장소가 설정되지 않았습니다."
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{_API}/repos/{repo}/contents/{path}"
    try:
        # 기존 파일의 sha 조회 (갱신 시 필요, 없으면 신규 생성)
        sha = None
        r = requests.get(url, headers=headers, params={"ref": branch}, timeout=_TIMEOUT)
        if r.status_code == 200:
            sha = r.json().get("sha")
        elif r.status_code not in (404,):
            return False, f"조회 실패: {r.status_code} {r.text[:160]}"

        body = {
            "message": message,
            "content": base64.b64encode(content_str.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        r2 = requests.put(url, headers=headers, json=body, timeout=_TIMEOUT)
        if r2.status_code in (200, 201):
            return True, "GitHub 저장 완료"
        return False, f"저장 실패: {r2.status_code} {r2.text[:200]}"
    except Exception as e:
        return False, f"저장 오류: {e}"


def read_file(repo: str, path: str, token: str, branch: str = "main") -> str | None:
    """repo의 path 파일 내용을 문자열로 반환. 실패 시 None."""
    if not token or not repo:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.get(f"{_API}/repos/{repo}/contents/{path}",
                         headers=headers, params={"ref": branch}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        return base64.b64decode(r.json().get("content", "")).decode("utf-8")
    except Exception:
        return None
