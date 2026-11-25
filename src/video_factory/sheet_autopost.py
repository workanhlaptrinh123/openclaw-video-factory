# -*- coding: utf-8 -*-
"""Google Sheet Auto-Approval Worker (PhongBanAI PA -> PD -> POSTED flow).

Columns (tab `aid_video`):
  A: Tiêu đề | B: Caption | C: Link video | D: Facebook | E: YouTube | F: Link bài | G: Ghi chú

Status flow:
  PA (Pending Approval) -> customer changes to PD (Approved) -> worker publishes -> POSTED + Link bài.

Usage:
  python sheet_autopost.py --add --video path.mp4 --title "..." --caption "..."
  python sheet_autopost.py --run-once
"""
import argparse
import json
from pathlib import Path

from publish_social import load_cfg, post_facebook, post_youtube

ROOT = Path(__file__).resolve().parent


def _get_gspread_client(cfg: dict):
    import gspread

    oauth_file = ROOT / "secrets" / "token_google_oauth.json"
    if oauth_file.is_file():
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(oauth_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            oauth_file.write_text(creds.to_json(), encoding="utf-8")
        return gspread.authorize(creds)

    gs = cfg.get("google_sheet") or {}
    sa_file = Path(gs.get("credentials_file") or (ROOT / "secrets" / "googlesheetcn.json"))
    if sa_file.is_file():
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return gspread.authorize(Credentials.from_service_account_file(str(sa_file), scopes=scopes))

    raise RuntimeError("Chưa có Google OAuth token hoặc Service Account JSON.")


def _open_tab(cfg: dict):
    gs = cfg.get("google_sheet") or {}
    sheet_id = (gs.get("sheet_id") or "").strip()
    tab_name = gs.get("tab") or "aid_video"
    if not sheet_id:
        raise RuntimeError("Chưa cấu hình Google Sheet ID trong social_config.json.")
    gc = _get_gspread_client(cfg)
    sh = gc.open_by_key(sheet_id)
    try:
        return sh.worksheet(tab_name)
    except Exception:
        ws = sh.add_worksheet(title=tab_name, rows=200, cols=10)
        ws.append_row(["Tiêu đề", "Caption", "Link video", "Facebook", "YouTube", "Link bài", "Ghi chú"])
        return ws


def add_pending_row(title: str, caption: str, video: str, note: str = "") -> dict:
    cfg = load_cfg()
    ws = _open_tab(cfg)
    fb_st = "PA" if (cfg.get("facebook") or {}).get("enabled") else ""
    yt_st = "PA" if (cfg.get("youtube") or {}).get("enabled") else ""
    ws.append_row([title, caption, video, fb_st, yt_st, "", note])
    return {"ok": True, "action": "added", "facebook": fb_st, "youtube": yt_st}


def run_once() -> dict:
    cfg = load_cfg()
    ws = _open_tab(cfg)
    rows = ws.get_all_values()
    processed = []
    for row_idx, r in enumerate(rows[1:], start=2):
        r = r + [""] * (7 - len(r))
        title, caption, video_str, fb_st, yt_st, post_link, note = r[:7]
        if fb_st.strip().upper() != "PD" and yt_st.strip().upper() != "PD":
            continue
        vpath = Path(video_str.strip())
        links = [x.strip() for x in post_link.splitlines() if x.strip()]
        notes = [note.strip()] if note.strip() else []

        if fb_st.strip().upper() == "PD":
            res = post_facebook(cfg, title, caption or title, vpath)
            if res.get("ok"):
                ws.update_cell(row_idx, 4, "POSTED")
                if res.get("url"):
                    links.append(res["url"])
            else:
                ws.update_cell(row_idx, 4, "ERROR")
                notes.append("FB: " + str(res.get("error"))[:120])
            processed.append({"row": row_idx, "channel": "facebook", **res})

        if yt_st.strip().upper() == "PD":
            res = post_youtube(cfg, title, caption or title, vpath)
            if res.get("ok"):
                ws.update_cell(row_idx, 5, "POSTED")
                if res.get("url"):
                    links.append(res["url"])
            else:
                ws.update_cell(row_idx, 5, "ERROR")
                notes.append("YT: " + str(res.get("error"))[:120])
            processed.append({"row": row_idx, "channel": "youtube", **res})

        ws.update_cell(row_idx, 6, "\n".join(links))
        if notes:
            ws.update_cell(row_idx, 7, " | ".join(notes)[:300])

    return {"ok": True, "processed_count": len(processed), "results": processed}


def main():
    ap = argparse.ArgumentParser(description="Google Sheet PA -> PD -> POSTED auto-publisher")
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--run-once", action="store_true")
    ap.add_argument("--video", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    try:
        if a.add:
            out = add_pending_row(a.title, a.caption, a.video, a.note)
        elif a.run_once:
            out = run_once()
        else:
            out = {"ok": False, "error": "Specify --add or --run-once"}
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
