# -*- coding: utf-8 -*-
"""Social auto-publisher for OpenClaw Video Factory: Google Sheet, Facebook Fanpage, YouTube."""
import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG_FILE = ROOT / "social_config.json"


def load_cfg() -> dict:
    if not CFG_FILE.is_file():
        return {}
    return json.loads(CFG_FILE.read_text(encoding="utf-8-sig"))


def log_to_sheet(cfg: dict, title: str, caption: str, video_path: str, fb_status: str = "PA", yt_status: str = "PA", post_link: str = "", note: str = "") -> dict:
    gs = cfg.get("google_sheet") or {}
    sheet_id = (gs.get("sheet_id") or "").strip()
    cred_path = Path(gs.get("credentials_file") or (ROOT / "secrets" / "googlesheetcn.json"))
    tab_name = gs.get("tab") or "aid_video"
    if not sheet_id or not cred_path.is_file():
        return {"ok": False, "error": "Chưa cấu hình Google Sheet ID hoặc file Service Account JSON."}

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(str(cred_path), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        ws = sh.add_worksheet(title=tab_name, rows=200, cols=10)
        ws.append_row(["Tiêu đề", "Caption", "Link video", "Facebook", "YouTube", "Link bài", "Ghi chú"])
    row = [title, caption, str(video_path), fb_status, yt_status, post_link, note]
    ws.append_row(row)
    return {"ok": True, "sheet_id": sheet_id, "tab": tab_name}


def post_facebook(cfg: dict, title: str, caption: str, video_path: Path) -> dict:
    fb = cfg.get("facebook") or {}
    if not fb.get("enabled"):
        return {"ok": False, "error": "Tự động đăng Facebook đang tắt trong cấu hình."}
    page_id = (fb.get("page_id") or "").strip()
    token = (fb.get("page_access_token") or "").strip()
    if not page_id or not token:
        return {"ok": False, "error": "Thiếu Facebook PAGE_ID hoặc PAGE_ACCESS_TOKEN."}
    if not video_path.is_file():
        return {"ok": False, "error": f"Không tìm thấy file video: {video_path}"}

    import requests

    url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"
    with video_path.open("rb") as f:
        resp = requests.post(
            url,
            data={"access_token": token, "title": title, "description": caption},
            files={"source": (video_path.name, f, "video/mp4")},
            timeout=300,
        )
    data = resp.json()
    if resp.status_code >= 400 or "error" in data:
        return {"ok": False, "error": str(data.get("error") or resp.text)[:400]}
    vid_id = data.get("id", "")
    return {"ok": True, "platform": "facebook", "id": vid_id, "url": f"https://www.facebook.com/{page_id}/videos/{vid_id}"}


def post_youtube(cfg: dict, title: str, caption: str, video_path: Path, privacy: str = "public") -> dict:
    yt = cfg.get("youtube") or {}
    if not yt.get("enabled"):
        return {"ok": False, "error": "Tự động đăng YouTube đang tắt trong cấu hình."}
    client_id = (yt.get("client_id") or "").strip()
    client_secret = (yt.get("client_secret") or "").strip()
    token_file = ROOT / "secrets" / "token_youtube_oauth.json"
    if not client_id or not client_secret:
        return {"ok": False, "error": "Thiếu YOUTUBE_CLIENT_ID hoặc YOUTUBE_CLIENT_SECRET."}
    if not video_path.is_file():
        return {"ok": False, "error": f"Không tìm thấy file video: {video_path}"}

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    if token_file.is_file():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_cfg = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_cfg, scopes)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title[:100], "description": caption, "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = req.execute()
    vid_id = resp.get("id", "")
    return {"ok": True, "platform": "youtube", "id": vid_id, "url": f"https://youtube.com/shorts/{vid_id}"}


def main():
    ap = argparse.ArgumentParser(description="Auto-publish video to Google Sheet, Facebook, YouTube")
    ap.add_argument("--channel", required=True, choices=["sheet", "facebook", "youtube"])
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--caption", default="")
    ap.add_argument("--privacy", default="public")
    a = ap.parse_args()
    cfg = load_cfg()
    try:
        if a.channel == "sheet":
            res = log_to_sheet(cfg, a.title, a.caption or a.title, str(a.video))
        elif a.channel == "facebook":
            res = post_facebook(cfg, a.title, a.caption or a.title, a.video)
        else:
            res = post_youtube(cfg, a.title, a.caption or a.title, a.video, a.privacy)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
