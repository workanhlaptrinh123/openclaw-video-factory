# -*- coding: utf-8 -*-
"""7-step installation engine with automatic Codex self-healing & rollback."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

from codex_healer import auto_heal
from openclaw_detect import OpenClawEnv
from openclaw_merge import grant_exec_approvals, merge_openclaw_config, restore_latest_backup

STEPS = [
    "Kiểm tra OpenClaw & sao lưu cấu hình",
    "Kiểm tra môi trường (Python 3.12, Node.js, FFmpeg)",
    "Cài đặt Video Factory & bộ skill OpenClaw",
    "Cài thư viện Python (.venv) & HyperFrames",
    "Ghép cấu hình OpenClaw & cấp quyền toàn phần",
    "Kiểm tra hợp lệ & khởi động lại Gateway",
    "Xác nhận bot đã sẵn sàng nhận lệnh",
]


@dataclass
class InstallOptions:
    env: OpenClawEnv
    mode: str = "separate_bot"  # "separate_bot" | "existing_bot"
    bot_token: str = ""
    owner_ids: List[str] = None
    api_key: str = ""
    pexels_key: str = ""
    enable_codex_heal: bool = True
    # Modular selection flags (Cài từng phần)
    install_video_core: bool = True
    install_google: bool = False
    install_facebook: bool = False
    install_youtube: bool = False
    # Auto-publish channels (Google Sheet / Drive / Facebook / YouTube)
    google_sheet_url: str = ""
    google_cred_json: str = ""
    google_drive_url: str = ""
    fb_page_id: str = ""
    fb_page_token: str = ""
    fb_enabled: bool = False
    yt_channel_url: str = ""
    yt_client_id: str = ""
    yt_client_secret: str = ""
    yt_enabled: bool = False


def extract_sheet_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", s)
    return m.group(1) if m else s


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _run(cmd, cwd=None, timeout=300, env=None):
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def _find_python312() -> str:
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local_app / "Programs" / "Python" / "Python312" / "python.exe",
        Path(r"C:\Program Files\Python312\python.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    if shutil.which("py"):
        r = _run(["py", "-3.12", "-c", "import sys; print(sys.executable)"], timeout=15)
        if r.returncode == 0 and r.stdout.strip() and Path(r.stdout.strip()).is_file():
            return r.stdout.strip()
    py = shutil.which("python")
    return py or ""


def run_install(
    opts: InstallOptions,
    on_step: Callable[[int, str, str], None],
    on_log: Callable[[str], None],
) -> bool:
    """Execute all 7 installation steps with optional Codex self-healing."""
    sd = Path(opts.env.state_dir)
    vf_dir = sd / "video-factory"
    secrets = [opts.bot_token, opts.api_key, opts.pexels_key]
    py_exe = {"path": ""}

    def exec_with_heal(idx: int, fn: Callable[[], None]):
        title = STEPS[idx]
        on_step(idx, "running", "Đang thực hiện...")
        on_log(f"\n=== Bước {idx + 1}/7: {title} ===")
        for attempt in range(2):
            try:
                fn()
                on_step(idx, "done", "Hoàn tất")
                on_log(f"✓ Hoàn tất bước {idx + 1}: {title}")
                return
            except Exception as exc:
                err_text = str(exc)
                on_log(f"✗ Lỗi bước {idx + 1}: {err_text}")
                if attempt == 0 and opts.enable_codex_heal:
                    on_step(idx, "healing", "Codex đang tự chẩn đoán & sửa lỗi...")
                    ok, msg = auto_heal(
                        opts.env.codex_cmd,
                        opts.api_key,
                        title,
                        err_text,
                        str(sd),
                        secrets,
                        on_log,
                    )
                    if ok:
                        on_log("↻ Đang thử chạy lại bước vừa sửa...")
                        continue
                    on_log(f"  Codex tự sửa chưa thành công: {msg[:200]}")
                on_step(idx, "error", err_text[:120])
                raise

    try:
        # Step 1: Verify OpenClaw & backup
        def s1():
            if not any([opts.install_video_core, opts.install_google, opts.install_facebook, opts.install_youtube]):
                raise RuntimeError("Vui lòng tích chọn ít nhất 1 module để cài đặt.")
            if not opts.env.found or not Path(opts.env.config_path).is_file():
                raise RuntimeError("Không tìm thấy OpenClaw trên máy này. Vui lòng cài OpenClaw trước.")
            if opts.install_video_core and opts.mode == "separate_bot" and not opts.bot_token.strip():
                raise RuntimeError("Chế độ Bot riêng yêu cầu nhập Telegram Bot Token.")
            mods = [name for flag, name in [
                (opts.install_video_core, "Tạo Video 9:16"),
                (opts.install_google, "Google Sheet/Drive"),
                (opts.install_facebook, "Facebook Fanpage"),
                (opts.install_youtube, "YouTube Shorts"),
            ] if flag]
            on_log(f"  Module đã chọn: {', '.join(mods)}")
            on_log(f"  OpenClaw state: {sd}")
            on_log(f"  OpenClaw CLI:   {opts.env.openclaw_cmd}")
            on_log(f"  Codex CLI:      {opts.env.codex_cmd or '(dùng Codex API dự phòng)'}")

        exec_with_heal(0, s1)

        # Step 2: Check Python 3.12, Node, FFmpeg
        def s2():
            py = _find_python312()
            if not py:
                on_log("  Không thấy Python 3.12 — đang cài tự động qua winget...")
                r = _run(["winget", "install", "-e", "--id", "Python.Python.3.12", "--scope", "user",
                          "--accept-package-agreements", "--accept-source-agreements"], timeout=300)
                if r.returncode != 0:
                    raise RuntimeError("Không cài được Python 3.12: " + (r.stderr or r.stdout)[-300:])
                py = _find_python312()
            if not py:
                raise RuntimeError("Không tìm thấy python.exe sau khi cài.")
            py_exe["path"] = py
            on_log(f"  Python: {py}")

            if opts.install_video_core:
                node = shutil.which("node")
                if not node:
                    raise RuntimeError("Không tìm thấy Node.js trên PATH.")
                on_log(f"  Node:   {node}")

                ffmpeg = shutil.which("ffmpeg")
                if not ffmpeg:
                    on_log("  Không thấy FFmpeg — đang cài tự động qua winget...")
                    r = _run(["winget", "install", "-e", "--id", "Gyan.FFmpeg",
                              "--accept-package-agreements", "--accept-source-agreements"], timeout=300)
                    if r.returncode != 0:
                        raise RuntimeError("Không cài được FFmpeg: " + (r.stderr or r.stdout)[-300:])
                else:
                    on_log(f"  FFmpeg: {ffmpeg}")

        exec_with_heal(1, s2)

        # Step 3: Copy selected core/social files + parameterized skills
        def s3():
            src_vf = bundle_root() / "src" / "video_factory"
            src_skill = bundle_root() / "src" / "skill"
            for sub in ("config", "assets/fonts", "templates/fast-reel", "scripts_in", "workspaces", "output", "secrets"):
                (vf_dir / sub).mkdir(parents=True, exist_ok=True)

            if opts.install_video_core:
                for rel in (
                    "make_reel.py",
                    "package.json",
                    "config/pronunciation.json",
                    "assets/fonts/BeVietnamPro-Regular.ttf",
                    "assets/fonts/BeVietnamPro-Bold.ttf",
                    "templates/fast-reel/index.template.html",
                    "templates/fast-reel/styles.css",
                ):
                    shutil.copy2(src_vf / rel, vf_dir / rel)

            if opts.install_google or opts.install_facebook or opts.install_youtube:
                shutil.copy2(src_vf / "publish_social.py", vf_dir / "publish_social.py")

            # Merge into existing social_config.json so previously configured channels are preserved
            soc_path = vf_dir / "social_config.json"
            social_cfg = json.loads(soc_path.read_text(encoding="utf-8-sig")) if soc_path.is_file() else {}

            if opts.install_google:
                cred_dst = vf_dir / "secrets" / "googlesheetcn.json"
                if opts.google_cred_json.strip() and Path(opts.google_cred_json.strip()).is_file():
                    shutil.copy2(Path(opts.google_cred_json.strip()), cred_dst)
                social_cfg["google_sheet"] = {
                    "url": opts.google_sheet_url.strip(),
                    "sheet_id": extract_sheet_id(opts.google_sheet_url),
                    "tab": "aid_video",
                    "credentials_file": str(cred_dst),
                }
                social_cfg["google_drive"] = {"folder_url": opts.google_drive_url.strip()}
                on_log("  Đã lưu cấu hình Google Sheet / Drive.")

            if opts.install_facebook:
                social_cfg["facebook"] = {
                    "enabled": True,
                    "page_id": opts.fb_page_id.strip(),
                    "page_access_token": opts.fb_page_token.strip(),
                }
                on_log("  Đã lưu cấu hình tự động đăng Facebook Fanpage.")

            if opts.install_youtube:
                social_cfg["youtube"] = {
                    "enabled": True,
                    "channel_url": opts.yt_channel_url.strip(),
                    "client_id": opts.yt_client_id.strip(),
                    "client_secret": opts.yt_client_secret.strip(),
                }
                on_log("  Đã lưu cấu hình tự động đăng YouTube Shorts.")

            if social_cfg:
                soc_path.write_text(json.dumps(social_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            # Write .env if Pexels or Codex key provided
            if opts.install_video_core:
                env_lines = []
                if opts.api_key.strip():
                    env_lines.append(f"TOKEN_CODEX_API_KEY={opts.api_key.strip()}")
                    subprocess.run(
                        ["powershell", "-NoLogo", "-NoProfile", "-Command",
                         f"[Environment]::SetEnvironmentVariable('TOKEN_CODEX_API_KEY', '{opts.api_key.strip()}', 'User')"],
                        capture_output=True, timeout=20, stdin=subprocess.DEVNULL,
                    )
                if opts.pexels_key.strip():
                    env_lines.append(f"PEXELS_API_KEY={opts.pexels_key.strip()}")
                if env_lines:
                    (vf_dir / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

            def render_tpl(src_file: Path, dst_file: Path):
                txt = src_file.read_text(encoding="utf-8")
                txt = txt.replace("{{VIDEO_FACTORY_DIR}}", str(vf_dir)).replace("{{OPENCLAW_STATE_DIR}}", str(sd))
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                dst_file.write_text(txt, encoding="utf-8")

            render_tpl(src_skill / "SKILL.md", sd / "workspace" / "skills" / "tao-video-reel" / "SKILL.md")
            ws_vid = sd / "workspace-video"
            if opts.mode == "separate_bot" or ws_vid.is_dir():
                render_tpl(src_skill / "SKILL.md", ws_vid / "skills" / "tao-video-reel" / "SKILL.md")
                if opts.install_video_core:
                    render_tpl(src_skill / "AGENTS.md", ws_vid / "AGENTS.md")
                    render_tpl(src_skill / "IDENTITY.md", ws_vid / "IDENTITY.md")
            on_log(f"  Đã cập nhật file & Skill tại {vf_dir}")

        exec_with_heal(2, s3)

        # Step 4: Selective Python venv packages + npm install hyperframes (only if needed)
        def s4():
            venv_py = vf_dir / ".venv" / "Scripts" / "python.exe"
            if not venv_py.is_file():
                on_log("  Đang tạo môi trường ảo Python (.venv)...")
                r = _run([py_exe["path"], "-m", "venv", str(vf_dir / ".venv")], timeout=120)
                if r.returncode != 0:
                    raise RuntimeError("Tạo venv thất bại: " + (r.stderr or r.stdout)[-300:])

            pkgs = ["requests", "python-dotenv"]
            if opts.install_video_core:
                pkgs += ["edge-tts", "gTTS", "Pillow"]
            if opts.install_google:
                pkgs += ["gspread", "google-auth"]
            if opts.install_youtube:
                pkgs += ["google-api-python-client", "google-auth-oauthlib"]
            pkgs = list(dict.fromkeys(pkgs))
            on_log(f"  Đang cài gói Python cho các module đã chọn: {', '.join(pkgs)}...")
            r = _run([str(venv_py), "-m", "pip", "install", "--quiet", *pkgs], timeout=360)
            if r.returncode != 0:
                raise RuntimeError("pip install thất bại: " + (r.stderr or r.stdout)[-300:])

            if opts.install_video_core:
                npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
                if not npm_cmd:
                    raise RuntimeError("Không tìm thấy npm trên PATH.")
                on_log("  Đang cài hyperframes & gsap (npm install)...")
                r = _run([npm_cmd, "install", "--no-audit", "--no-fund"], cwd=vf_dir, timeout=420)
                if r.returncode != 0:
                    raise RuntimeError("npm install thất bại: " + (r.stderr or r.stdout)[-300:])
            else:
                on_log("  Bỏ qua npm install (chỉ cài bổ sung module đăng bài).")

        exec_with_heal(3, s4)

        # Step 5: Merge openclaw.json & grant exec approvals (only when video core selected)
        if opts.install_video_core:
            def s5():
                owners = [x.strip() for x in (opts.owner_ids or []) if x.strip()]
                bak = merge_openclaw_config(
                    state_dir=sd,
                    mode=opts.mode,
                    bot_token=opts.bot_token,
                    owner_ids=owners,
                    api_key=opts.api_key,
                )
                on_log(f"  Đã sao lưu openclaw.json -> {bak.name}")
                agents_to_grant = ["main", "video-creator"] if opts.mode == "separate_bot" else ["main"]
                ok, msg = grant_exec_approvals(opts.env.openclaw_cmd, sd, agents_to_grant)
                on_log(f"  Exec approvals: {msg}")
                if not ok:
                    raise RuntimeError(f"Không cập nhật được exec approvals: {msg}")

            exec_with_heal(4, s5)

            # Step 6: Validate config & restart gateway persistently
            def s6():
                r = _run([opts.env.openclaw_cmd, "config", "validate"], timeout=45)
                if r.returncode != 0:
                    restore_latest_backup(sd)
                    raise RuntimeError("openclaw.json không hợp lệ (đã tự khôi phục backup): " + (r.stderr or r.stdout)[-400:])
                on_log("  openclaw config validate: HỢP LỆ ✓")

                if opts.env.has_instance_ps1:
                    on_log("  Đang dừng gateway cũ và khởi chạy lại ở chế độ chạy nền...")
                    _run(["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", str(sd / "openclaw-instance.ps1"), "gateway", "stop"], timeout=45)
                    time.sleep(2)
                    if opts.env.startup_vbs and Path(opts.env.startup_vbs).is_file():
                        cmd_str = f'wscript.exe "{opts.env.startup_vbs}"'
                        _run(["powershell", "-NoLogo", "-NoProfile", "-Command",
                              f'Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = \'{cmd_str}\' }} | Out-Null'],
                             timeout=30)
                    else:
                        ps_cmd = f'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{sd}\\openclaw-instance.ps1" gateway start'
                        _run(["powershell", "-NoLogo", "-NoProfile", "-Command",
                              f'Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = \'{ps_cmd}\' }} | Out-Null'],
                             timeout=30)
                else:
                    _run([opts.env.openclaw_cmd, "gateway", "restart"], timeout=60)

            exec_with_heal(5, s6)

            # Step 7: Verify agents & gateway ready
            def s7():
                on_log("  Đang chờ Gateway mở cổng và kiểm tra danh sách agent...")
                time.sleep(10)
                r = _run([opts.env.openclaw_cmd, "agents", "list", "--bindings"], timeout=45)
                if r.returncode != 0:
                    raise RuntimeError("Không đọc được danh sách agent: " + (r.stderr or r.stdout)[-300:])
                on_log(r.stdout.strip())

            exec_with_heal(6, s7)
        else:
            on_step(4, "skipped", "Giữ nguyên OpenClaw cũ")
            on_step(5, "skipped", "Không cần khởi động lại Gateway")
            on_step(6, "done", "Đã cập nhật module bổ sung")
            on_log("\n✓ Hoàn tất cài đặt/cập nhật các module bổ sung (không làm gián đoạn OpenClaw đang chạy).")
        return True
    except Exception:
        return False
