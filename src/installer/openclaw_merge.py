# -*- coding: utf-8 -*-
"""Safe OpenClaw config merger, exec-approvals updater, and rollback helper."""
import copy
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Tuple


def _merge_unique(lst: list, items: List[str]) -> list:
    out = list(lst) if isinstance(lst, list) else []
    for x in items:
        if x and x not in out:
            out.append(x)
    return out


def backup_config(config_path: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = config_path.with_name(f"openclaw.json.bak-videofactory-{ts}")
    shutil.copy2(config_path, bak)
    return bak


def restore_latest_backup(state_dir: Path) -> Tuple[bool, str]:
    config_path = state_dir / "openclaw.json"
    backups = sorted(state_dir.glob("openclaw.json.bak-videofactory-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return False, "Không tìm thấy bản sao lưu openclaw.json.bak-videofactory-*"
    latest = backups[0]
    shutil.copy2(latest, config_path)
    return True, f"Đã khôi phục cấu hình từ {latest.name}"


def merge_openclaw_config(
    state_dir: Path,
    mode: str,  # "separate_bot" or "existing_bot"
    bot_token: str,
    owner_ids: List[str],
    api_key: str,
    account_id: str = "trolyvideo",
    agent_id: str = "video-creator",
) -> Path:
    """Safely merge Video Factory agent/bot into openclaw.json without breaking existing bots."""
    config_path = state_dir / "openclaw.json"
    bak = backup_config(config_path)
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))

    # 1. Ensure owners have full access
    if owner_ids:
        cmds = cfg.setdefault("commands", {})
        cmds["ownerAllowFrom"] = _merge_unique(
            cmds.get("ownerAllowFrom", []),
            [f"telegram:{oid}" for oid in owner_ids],
        )

    # 2. Ensure API key is stored if member-provider.secret doesn't exist
    secret_file = state_dir / "member-provider.secret"
    if api_key.strip() and not secret_file.is_file():
        secret_file.write_text(api_key.strip() + "\n", encoding="utf-8")

    # 3. Separate bot mode: add telegram account + video-creator agent + binding
    if mode == "separate_bot":
        token_file = state_dir / "telegram-video.token"
        token_file.write_text(bot_token.strip() + "\n", encoding="utf-8")

        tg = cfg.setdefault("channels", {}).setdefault("telegram", {})
        tg["enabled"] = True
        tg["mediaMaxMb"] = max(int(tg.get("mediaMaxMb") or 0), 50)
        if owner_ids:
            tg["allowFrom"] = _merge_unique(tg.get("allowFrom", []), owner_ids)
            ea = tg.setdefault("execApprovals", {"enabled": "auto", "approvers": [], "target": "dm"})
            ea["approvers"] = _merge_unique(ea.get("approvers", []), owner_ids)

        accounts = tg.setdefault("accounts", {})
        accounts[account_id] = {
            "allowFrom": list(owner_ids) if owner_ids else ["*"],
            "groupPolicy": "allowlist",
            "dmPolicy": "pairing",
            "groupAllowFrom": ["*"],
            "tokenFile": str(token_file),
            "enabled": True,
            "mediaMaxMb": 50,
            "execApprovals": {
                "enabled": "auto",
                "approvers": list(owner_ids),
                "target": "dm",
            },
        }

        # Preserve main agent workspace explicitly before switching to multi-agent explicit ownership
        agents = cfg.setdefault("agents", {})
        agents["ownership"] = "explicit"
        defaults = agents.setdefault("defaults", {})
        main_ws = defaults.get("workspace") or str(state_dir / "workspace")
        defaults.setdefault("systemAgent", {"agentId": "main"})

        entries = agents.setdefault("entries", {})
        if "main" in entries and isinstance(entries["main"], dict):
            entries["main"].setdefault("workspace", main_ws)
        else:
            entries["main"] = {"workspace": main_ws}

        entries[agent_id] = {
            "name": "Trợ Lý Video",
            "workspace": str(state_dir / "workspace-video"),
            "tools": {
                "exec": {
                    "host": "gateway",
                    "mode": "full",
                    "strictInlineEval": False,
                },
                "toolsBySender": {
                    "*": {
                        "alsoAllow": ["exec", "process", "group:fs"]
                    }
                },
            },
        }

        # Binding
        bindings = cfg.setdefault("bindings", [])
        exists = any(
            (b.get("match") or {}).get("channel") == "telegram"
            and (b.get("match") or {}).get("accountId") == account_id
            for b in bindings
        )
        if not exists:
            bindings.append({
                "agentId": agent_id,
                "match": {"channel": "telegram", "accountId": account_id},
            })

        # Approvals targets & agentFilter
        approvals = cfg.setdefault("approvals", {})
        for section in ("exec", "plugin"):
            sec = approvals.get(section)
            if isinstance(sec, dict):
                af = sec.get("agentFilter")
                if isinstance(af, list) and agent_id not in af:
                    af.append(agent_id)
                targets = sec.get("targets")
                if isinstance(targets, list):
                    for oid in owner_ids:
                        t_obj = {"channel": "telegram", "to": oid, "accountId": account_id}
                        if t_obj not in targets:
                            targets.append(t_obj)

    config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bak


def grant_exec_approvals(openclaw_cmd: str, state_dir: Path, agent_ids: List[str]) -> Tuple[bool, str]:
    """Ensure target agent(s) have full exec permissions in OpenClaw exec_approvals_config."""
    no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        res = subprocess.run(
            [openclaw_cmd, "approvals", "get", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
            stdin=subprocess.DEVNULL, creationflags=no_win,
        )
        if res.returncode != 0 or not res.stdout.strip():
            # Build baseline file if get failed
            doc = {
                "version": 1,
                "socket": {"path": str(state_dir / "exec-approvals.sock")},
                "defaults": {"security": "allowlist", "ask": "on-miss", "askFallback": "deny", "autoAllowSkills": False},
                "agents": {},
            }
        else:
            parsed = json.loads(res.stdout)
            doc = copy.deepcopy(parsed.get("file") or {})
            doc.setdefault("version", 1)
            doc.setdefault("agents", {})

        for aid in agent_ids:
            doc["agents"][aid] = {
                "security": "full",
                "ask": "off",
                "askFallback": "full",
                "autoAllowSkills": True,
                "allowlist": [],
            }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(doc, tf, ensure_ascii=False, indent=2)
            tmp_path = tf.name

        try:
            set_res = subprocess.run(
                [openclaw_cmd, "approvals", "set", "--file", tmp_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
                stdin=subprocess.DEVNULL, creationflags=no_win,
            )
            if set_res.returncode != 0:
                return False, (set_res.stderr or set_res.stdout)[-400:]
            return True, f"Đã cấp quyền exec toàn phần (full) cho: {', '.join(agent_ids)}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except Exception as exc:
        return False, str(exc)
