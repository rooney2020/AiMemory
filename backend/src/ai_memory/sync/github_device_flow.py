from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib import error, parse, request


GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
NETWORK_TIMEOUT_SECONDS = 30


class GitHubDeviceFlowError(RuntimeError):
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


@dataclass
class DeviceFlowStart:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass
class DeviceFlowToken:
    access_token: str
    token_type: str
    scope: str


def start_device_flow(client_id: str, scope: str = "repo") -> DeviceFlowStart:
    payload = _post_form(
        GITHUB_DEVICE_CODE_URL,
        {
            "client_id": client_id,
            "scope": scope,
        },
    )
    return DeviceFlowStart(
        device_code=payload["device_code"],
        user_code=payload["user_code"],
        verification_uri=payload.get("verification_uri") or payload.get("verification_uri_complete") or "https://github.com/login/device",
        expires_in=int(payload.get("expires_in", 900)),
        interval=int(payload.get("interval", 5)),
    )


def poll_device_flow(client_id: str, device_code: str) -> DeviceFlowToken:
    payload = _post_form(
        GITHUB_ACCESS_TOKEN_URL,
        {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )
    if "error" in payload:
        raise GitHubDeviceFlowError(payload.get("error_description") or payload["error"], code=payload["error"])
    return DeviceFlowToken(
        access_token=payload["access_token"],
        token_type=payload.get("token_type", "bearer"),
        scope=payload.get("scope", "repo"),
    )


def fetch_github_user(access_token: str) -> dict[str, Any]:
    req = request.Request(
        GITHUB_USER_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "ai-memory-qt",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=NETWORK_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GitHubDeviceFlowError(detail or f"GitHub user API failed: HTTP {exc.code}", code="http_error") from exc
    except error.URLError as exc:
        raise GitHubDeviceFlowError(f"无法连接 GitHub: {exc.reason}", code="network_error") from exc


def _post_form(url: str, payload: dict[str, str]) -> dict[str, Any]:
    body = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ai-memory-qt",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=NETWORK_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GitHubDeviceFlowError(detail or f"GitHub device flow failed: HTTP {exc.code}", code="http_error") from exc
    except error.URLError as exc:
        raise GitHubDeviceFlowError(f"无法连接 GitHub: {exc.reason}", code="network_error") from exc