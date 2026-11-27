# -*- coding: utf-8 -*-
"""Two-tier Codex Self-Healing Engine (Codex CLI -> Direct Codex API fallback).

Always redacts Telegram bot tokens and API keys before sending any diagnostic context.
"""
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable, List, Tuple

CODEX_API_URL = "https://codex.anhlaptrinh.vn/v1/chat/completions"
CODEX_MODEL = "gpt-6.2-sol"


def redact_secrets(text: str, extra_secrets: List[str] = None) -> str:
    if not text:
        return ""
    out = text
    for sec in (extra_secrets or []):
        if sec and len(sec) >= 8:
            out = out.replace(sec, "***REDACTED***")
    # Redact Telegram tokens & sk- keys
    out = re.sub(r"\b\d{8,12}:[A-Za-z0-9_-]{25,}\b", "***TG_TOKEN***", out)
    out = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "***API_KEY***", out)
    return out


def _try_codex_cli(
    codex_cmd: str,
    api_key: str,
    step_name: str,
    error_log: str,
    work_dir: str,
    log_fn: Callable[[str], None],
) -> Tuple[bool, str]:
    """Tier 1: Invoke local Codex CLI (`codex exec`) to diagnose and fix."""
    if not codex_cmd or not Path(codex_cmd).is_file():
        return False, "codex.cmd không tồn tại trên máy"

    prompt = (
        f"Bạn là kỹ sư sửa lỗi tự động cho trình cài đặt OpenClaw Video Factory trên Windows.\n"
        f"Bước đang lỗi: {step_name}\n"
        f"Thư mục làm việc: {work_dir}\n"
        f"Log lỗi (đã ẩn bí mật):\n{error_log[-2500:]}\n\n"
        f"Hãy chẩn đoán ngắn gọn nguyên nhân và sửa trực tiếp lỗi đó một cách an toàn "
        f"(không xóa dữ liệu người dùng, không sửa bot cũ). Kết thúc bằng tóm tắt ngắn bằng tiếng Việt."
    )
    env = dict(os.environ)
    if api_key:
        env["OPENAI_API_KEY"] = api_key
        env["TOKEN_CODEX_API_KEY"] = api_key

    log_fn("  [Codex CLI] Đang gọi codex exec để tự chẩn đoán và sửa lỗi...")
    try:
        res = subprocess.run(
            [codex_cmd, "exec", "--full-auto", prompt],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (res.stdout or "") + "\n" + (res.stderr or "")
        if res.returncode == 0:
            log_fn("  [Codex CLI] Đã hoàn tất xử lý sửa lỗi.")
            return True, out[-600:]
        return False, f"codex CLI trả mã {res.returncode}: {out[-400:]}"
    except Exception as exc:
        return False, f"codex CLI lỗi khi chạy: {exc}"


def _try_codex_api(
    api_key: str,
    step_name: str,
    error_log: str,
    work_dir: str,
    log_fn: Callable[[str], None],
) -> Tuple[bool, str]:
    """Tier 2: Direct Codex API fallback when Codex CLI is unavailable or fails."""
    if not api_key:
        return False, "Chưa nhập API Key cho Codex nên không thể gọi Codex API dự phòng."

    log_fn("  [Codex API] Đang gọi API Codex (gpt-6.2-sol) phân tích và đề xuất lệnh sửa...")
    system_prompt = (
        "You are a Windows installer self-healing assistant for OpenClaw Video Factory. "
        "Return ONLY valid JSON: {\"diagnosis\": \"...\", \"commands\": [\"powershell command 1\", ...]}. "
        "Commands must be safe, idempotent Windows PowerShell commands (e.g. pip install, npm install, openclaw doctor --fix). "
        "Never delete user data, never touch secrets, max 3 commands."
    )
    user_prompt = (
        f"Failed step: {step_name}\n"
        f"Working directory: {work_dir}\n"
        f"Sanitized error:\n{error_log[-2500:]}"
    )
    body = json.dumps({
        "model": CODEX_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            CODEX_API_URL,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL).strip()
        plan = json.loads(content)
        diag = plan.get("diagnosis", "")
        cmds = plan.get("commands") or []
        log_fn(f"  [Codex API] Chẩn đoán: {diag}")
        if not cmds:
            return False, f"Codex API không đề xuất lệnh sửa: {diag}"

        for cmd in cmds[:3]:
            # Basic safety guard
            lower = cmd.lower()
            if any(bad in lower for bad in ("format ", "remove-item -recurse c:\\", "del /s /q c:\\", "rm -rf /")):
                log_fn(f"  [Codex API] Bỏ qua lệnh không an toàn: {cmd}")
                continue
            log_fn(f"  [Codex API] Chạy lệnh sửa: {cmd}")
            r = subprocess.run(
                ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                cwd=work_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode != 0:
                log_fn(f"  [Codex API] Lệnh trả mã {r.returncode}: {(r.stderr or r.stdout)[-200:]}")
        return True, diag
    except Exception as exc:
        return False, f"Codex API lỗi: {exc}"


def auto_heal(
    codex_cmd: str,
    api_key: str,
    step_name: str,
    error_log: str,
    work_dir: str,
    secrets_to_hide: List[str],
    log_fn: Callable[[str], None],
) -> Tuple[bool, str]:
    """Try Codex CLI first; if it fails or isn't installed, seamlessly fall back to Codex API."""
    clean_err = redact_secrets(error_log, secrets_to_hide)
    ok, msg = _try_codex_cli(codex_cmd, api_key, step_name, clean_err, work_dir, log_fn)
    if ok:
        return True, msg
    log_fn(f"  [Codex CLI không khả dụng/lỗi: {msg[:140]}] → Chuyển sang Codex API dự phòng...")
    return _try_codex_api(api_key, step_name, clean_err, work_dir, log_fn)
