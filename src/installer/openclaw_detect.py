# -*- coding: utf-8 -*-
"""Auto-detect an existing OpenClaw installation on Windows."""
import json
import os
import re
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class OpenClawEnv:
    found: bool = False
    openclaw_cmd: str = ""
    codex_cmd: str = ""
    state_dir: str = ""
    config_path: str = ""
    profile: str = ""
    existing_api_key: str = ""
    existing_owners: List[str] = field(default_factory=list)
    existing_agents: List[str] = field(default_factory=list)
    has_instance_ps1: bool = False
    startup_vbs: str = ""
    notes: List[str] = field(default_factory=list)


def _parse_openclaw_cmd(cmd_path: Path) -> dict:
    info = {}
    try:
        text = cmd_path.read_text(encoding="utf-8", errors="replace")
        for key in ("OPENCLAW_STATE_DIR", "OPENCLAW_CONFIG_PATH", "OPENCLAW_WORKSPACE_DIR", "OPENCLAW_PROFILE"):
            m = re.search(rf'set\s+"{key}=([^"]+)"', text, re.IGNORECASE)
            if m:
                info[key] = m.group(1).strip()
    except OSError:
        pass
    return info


def detect_openclaw() -> OpenClawEnv:
    env = OpenClawEnv()
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    user_home = Path(os.environ.get("USERPROFILE", str(Path.home())))

    # 1. Locate openclaw.cmd
    oc_candidates = [
        local_app / "OpenClaw" / "bin" / "openclaw.cmd",
        Path(shutil.which("openclaw") or ""),
    ]
    for c in oc_candidates:
        if c and str(c) and c.is_file():
            env.openclaw_cmd = str(c)
            break

    # 2. Locate codex.cmd
    cx_candidates = [
        local_app / "OpenClaw" / "bin" / "codex.cmd",
        Path(shutil.which("codex") or ""),
    ]
    for c in cx_candidates:
        if c and str(c) and c.is_file():
            env.codex_cmd = str(c)
            break

    # 3. Resolve state_dir and config_path
    parsed = _parse_openclaw_cmd(Path(env.openclaw_cmd)) if env.openclaw_cmd else {}
    state_dir = parsed.get("OPENCLAW_STATE_DIR") or os.environ.get("OPENCLAW_STATE_DIR") or ""
    config_path = parsed.get("OPENCLAW_CONFIG_PATH") or os.environ.get("OPENCLAW_CONFIG_PATH") or ""
    env.profile = parsed.get("OPENCLAW_PROFILE", "")

    if not config_path:
        for cand_dir in [Path(state_dir) if state_dir else None, user_home / "openclaw", user_home / ".openclaw"]:
            if cand_dir and (cand_dir / "openclaw.json").is_file():
                state_dir = str(cand_dir)
                config_path = str(cand_dir / "openclaw.json")
                break

    if config_path and Path(config_path).is_file():
        env.found = True
        env.state_dir = state_dir or str(Path(config_path).parent)
        env.config_path = config_path
        sd = Path(env.state_dir)
        env.has_instance_ps1 = (sd / "openclaw-instance.ps1").is_file()

        # Startup VBS
        appdata = Path(os.environ.get("APPDATA", ""))
        startup_dir = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if env.profile and (startup_dir / f"OpenClaw-{env.profile}.vbs").is_file():
            env.startup_vbs = str(startup_dir / f"OpenClaw-{env.profile}.vbs")
        elif startup_dir.is_dir():
            for f in startup_dir.glob("OpenClaw-*.vbs"):
                env.startup_vbs = str(f)
                break

        # Existing secret
        sec = sd / "member-provider.secret"
        if sec.is_file():
            try:
                env.existing_api_key = sec.read_text(encoding="utf-8-sig").strip()
            except OSError:
                pass
        if not env.existing_api_key:
            env.existing_api_key = os.environ.get("TOKEN_CODEX_API_KEY", "").strip()

        # Parse openclaw.json for owners & agents
        try:
            cfg = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
            owners = set()
            for item in (cfg.get("commands") or {}).get("ownerAllowFrom") or []:
                s = str(item)
                if s.startswith("telegram:"):
                    owners.add(s.split(":", 1)[1])
            for item in ((cfg.get("channels") or {}).get("telegram") or {}).get("allowFrom") or []:
                owners.add(str(item))
            env.existing_owners = sorted(o for o in owners if o and o != "*")

            entries = (cfg.get("agents") or {}).get("entries") or {}
            env.existing_agents = list(entries.keys())
        except Exception as exc:
            env.notes.append(f"Không đọc được JSON đầy đủ: {exc}")

    return env


def verify_telegram_token(token: str) -> dict:
    token = token.strip()
    if not token:
        return {"ok": False, "error": "Token trống"}
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url, headers={"User-Agent": "OpenClawVideoInstaller/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ok") and data.get("result"):
            r = data["result"]
            return {"ok": True, "username": r.get("username", ""), "first_name": r.get("first_name", ""), "id": r.get("id")}
        return {"ok": False, "error": str(data)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
