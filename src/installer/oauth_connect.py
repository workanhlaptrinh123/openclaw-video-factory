# -*- coding: utf-8 -*-
"""1-Click OAuth Connect for Google (Sheet + Drive + YouTube) and Facebook (Fanpage Picker).

Uses a temporary localhost HTTP callback server (http://127.0.0.1:18765/callback).
Zero third-party dependencies required (pure Python stdlib).
"""
import http.server
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Dict, List, Tuple

REDIRECT_PORT = 18765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
# Meta enforces HTTPS for all OAuth Redirect URIs (including Live mode).
# Static GitHub Pages relay forwards ?code=... locally in the user's browser to 127.0.0.1:18765/callback.
FACEBOOK_REDIRECT_URI = "https://workanhlaptrinh123.github.io/openclaw-video-factory/oauth-callback.html"

# Safe, zero-CASA-fee Google scopes (drive.file only touches files created by this app)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/youtube.upload",
]
FACEBOOK_SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
]


def load_bundled_oauth_config() -> dict:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for cand in (
        base / "src" / "installer" / "app_oauth_config.json",
        Path(__file__).resolve().parent / "app_oauth_config.json",
    ):
        if cand.is_file():
            try:
                return json.loads(cand.read_text(encoding="utf-8-sig"))
            except Exception:
                pass
    return {"google": {}, "facebook": {}}


def _wait_oauth_code(auth_url: str, timeout: int = 180) -> Tuple[bool, str]:
    result = {"code": "", "error": ""}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs:
                result["code"] = qs["code"][0]
                html_body = (
                    "<html><body style='font-family:Segoe UI,sans-serif;text-align:center;padding:48px;'>"
                    "<h2 style='color:#059669;'>✅ Đăng nhập thành công!</h2>"
                    "<p>Bạn có thể đóng tab này và quay lại cửa sổ OpenClaw Video Factory.</p>"
                    "</body></html>"
                )
            else:
                result["error"] = (qs.get("error_description") or qs.get("error") or ["Người dùng đã hủy đăng nhập"])[0]
                html_body = (
                    "<html><body style='font-family:Segoe UI,sans-serif;text-align:center;padding:48px;'>"
                    f"<h2 style='color:#DC2626;'>❌ Đăng nhập chưa hoàn tất</h2><p>{result['error']}</p>"
                    "</body></html>"
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_body.encode("utf-8"))
            done.set()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    server.timeout = 1.0
    th = threading.Thread(target=lambda: _serve_until(server, done, timeout), daemon=True)
    th.start()
    webbrowser.open(auth_url)
    done.wait(timeout)
    try:
        server.server_close()
    except Exception:
        pass
    if result["code"]:
        return True, result["code"]
    return False, result["error"] or "Hết thời gian chờ đăng nhập (180s)."


def _serve_until(server, done_event: threading.Event, timeout: int):
    deadline = time.time() + timeout
    while not done_event.is_set() and time.time() < deadline:
        server.handle_request()


def _http_post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_json(url: str, token: str, payload: dict = None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def connect_google_and_create_sheet(client_id: str, client_secret: str, secrets_dir: Path) -> Dict:
    """1-click Google OAuth -> saves refreshable token -> auto-creates 'Sổ Duyệt Video OpenClaw' Sheet."""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        return {
            "ok": False,
            "error": "Chưa cấu hình Google OAuth Client ID / Secret (xem docs/SETUP_OAUTH_APPS.md hoặc nhập ở mục YouTube Client ID / Secret).",
        }

    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    ok, code_or_err = _wait_oauth_code(auth_url)
    if not ok:
        return {"ok": False, "error": code_or_err}

    tok = _http_post_form("https://oauth2.googleapis.com/token", {
        "code": code_or_err,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    access_token = tok.get("access_token")
    if not access_token:
        return {"ok": False, "error": f"Không nhận được Google access_token: {tok}"}

    secrets_dir.mkdir(parents=True, exist_ok=True)
    token_file = secrets_dir / "token_google_oauth.json"
    saved = {
        "token": access_token,
        "refresh_token": tok.get("refresh_token", ""),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": GOOGLE_SCOPES,
    }
    token_file.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    # Auto-create Google Sheet "Sổ Duyệt Video OpenClaw" with tab aid_video
    sheet_url, sheet_id = "", ""
    try:
        created = _http_json(
            "https://sheets.googleapis.com/v4/spreadsheets",
            access_token,
            {
                "properties": {"title": "Sổ Duyệt Video OpenClaw"},
                "sheets": [{"properties": {"title": "aid_video"}}],
            },
        )
        sheet_id = created.get("spreadsheetId", "")
        sheet_url = created.get("spreadsheetUrl", "")
        if sheet_id:
            _http_json(
                f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/aid_video!A1:G1:append?valueInputOption=USER_ENTERED",
                access_token,
                {"values": [["Tiêu đề", "Caption", "Link video", "Facebook", "YouTube", "Link bài", "Ghi chú"]]},
            )
    except Exception:
        pass

    return {
        "ok": True,
        "token_file": str(token_file),
        "sheet_id": sheet_id,
        "sheet_url": sheet_url,
    }


def connect_facebook_get_pages(app_id: str, app_secret: str) -> Dict:
    """1-click Facebook Login -> exchanges for long-lived token -> returns customer's Fanpages."""
    app_id = app_id.strip()
    app_secret = app_secret.strip()
    if not app_id or not app_secret:
        return {
            "ok": False,
            "error": "Chưa cấu hình Meta App ID / Secret trong app_oauth_config.json (xem docs/SETUP_OAUTH_APPS.md).",
        }

    params = urllib.parse.urlencode({
        "client_id": app_id,
        "redirect_uri": FACEBOOK_REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(FACEBOOK_SCOPES),
    })
    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{params}"
    ok, code_or_err = _wait_oauth_code(auth_url)
    if not ok:
        return {"ok": False, "error": code_or_err}

    qs = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": FACEBOOK_REDIRECT_URI,
        "code": code_or_err,
    })
    with urllib.request.urlopen(f"https://graph.facebook.com/v21.0/oauth/access_token?{qs}", timeout=30) as r:
        short_tok = json.loads(r.read().decode("utf-8")).get("access_token", "")
    if not short_tok:
        return {"ok": False, "error": "Không lấy được Facebook access_token."}

    # Exchange for long-lived user token (60 days -> yields non-expiring Page Access Tokens)
    ll_qs = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_tok,
    })
    with urllib.request.urlopen(f"https://graph.facebook.com/v21.0/oauth/access_token?{ll_qs}", timeout=30) as r:
        user_tok = json.loads(r.read().decode("utf-8")).get("access_token", short_tok)

    # Fetch customer's managed Fanpages
    pages_qs = urllib.parse.urlencode({"access_token": user_tok, "fields": "id,name,access_token"})
    with urllib.request.urlopen(f"https://graph.facebook.com/v21.0/me/accounts?{pages_qs}", timeout=30) as r:
        pages_data = json.loads(r.read().decode("utf-8")).get("data", [])

    pages: List[dict] = [
        {"id": p["id"], "name": p.get("name", p["id"]), "access_token": p.get("access_token", "")}
        for p in pages_data
        if p.get("id") and p.get("access_token")
    ]
    if not pages:
        return {"ok": False, "error": "Tài khoản Facebook này chưa cấp quyền cho Fanpage nào."}
    return {"ok": True, "pages": pages}
