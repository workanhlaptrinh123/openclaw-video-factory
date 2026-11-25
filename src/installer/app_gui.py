# -*- coding: utf-8 -*-
"""Visual Step-by-Step Windows GUI Installer for OpenClaw Video Factory."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from codex_healer import auto_heal
from install_engine import InstallOptions, STEPS, run_install
from openclaw_detect import detect_openclaw, verify_telegram_token
from openclaw_merge import restore_latest_backup

BG = "#0f172a"
CARD = "#1e293b"
FG = "#f8fafc"
MUTED = "#94a3b8"
ACCENT = "#38bdf8"
GREEN = "#4ade80"
YELLOW = "#facc15"
RED = "#f87171"

ICONS = {
    "pending": ("⏳", MUTED),
    "running": ("🔄", ACCENT),
    "healing": ("🛠️", YELLOW),
    "done": ("✅", GREEN),
    "error": ("❌", RED),
}


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OpenClaw Video Factory — Cài đặt Tạo Video 9:16")
        self.geometry("860x760")
        self.minsize(780, 680)
        self.configure(bg=BG)

        self.env = detect_openclaw()
        self.installing = False
        self.step_labels = []
        self.step_details = []

        self._build_ui()
        self._populate_detected()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=CARD, background=ACCENT, thickness=10)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground=MUTED, padding=(14, 6), font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

        # Header
        hdr = tk.Frame(self, bg=BG, pady=10, padx=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬 OpenClaw Video Factory Installer", font=("Segoe UI", 16, "bold"), bg=BG, fg=FG).pack(anchor="w")
        self.banner_lbl = tk.Label(hdr, text="Đang kiểm tra OpenClaw trên máy...", font=("Segoe UI", 10), bg=BG, fg=ACCENT)
        self.banner_lbl.pack(anchor="w", pady=(4, 0))

        # Tabbed Config Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="x", padx=18, pady=(0, 8))

        # --- TAB 1: OpenClaw & Video ---
        cfg = tk.Frame(nb, bg=CARD, padx=16, pady=10)
        nb.add(cfg, text="1. OpenClaw & Tạo Video")

        # Mode selection
        mode_row = tk.Frame(cfg, bg=CARD)
        mode_row.pack(fill="x", pady=(0, 6))
        tk.Label(mode_row, text="Chế độ cài đặt:", font=("Segoe UI", 10, "bold"), bg=CARD, fg=FG).pack(side="left")
        self.mode_var = tk.StringVar(value="separate_bot")
        tk.Radiobutton(
            mode_row, text="Tạo Bot Video riêng (Khuyên dùng)", variable=self.mode_var, value="separate_bot",
            bg=CARD, fg=FG, selectcolor=BG, activebackground=CARD, activeforeground=FG, command=self._toggle_mode
        ).pack(side="left", padx=(12, 16))
        tk.Radiobutton(
            mode_row, text="Gắn vào Bot OpenClaw đang có", variable=self.mode_var, value="existing_bot",
            bg=CARD, fg=FG, selectcolor=BG, activebackground=CARD, activeforeground=FG, command=self._toggle_mode
        ).pack(side="left")

        # Form Grid (Tab 1)
        form = tk.Frame(cfg, bg=CARD)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        tk.Label(form, text="Telegram Bot Token:", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=3)
        self.token_var = tk.StringVar()
        self.token_entry = tk.Entry(form, textvariable=self.token_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9))
        self.token_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=3, ipady=3)
        self.check_tok_btn = tk.Button(form, text="Kiểm tra Bot", command=self._check_token, bg="#334155", fg=FG, relief="flat", padx=10, pady=2)
        self.check_tok_btn.grid(row=0, column=2, pady=3)

        tk.Label(form, text="Telegram ID chủ máy:", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=3)
        self.owner_var = tk.StringVar()
        tk.Entry(form, textvariable=self.owner_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3, ipady=3
        )

        tk.Label(form, text="API Key (Ảnh AI + Codex sửa lỗi):", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=3)
        self.api_var = tk.StringVar()
        tk.Entry(form, textvariable=self.api_var, show="*", bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3, ipady=3
        )

        tk.Label(form, text="Pexels API Key (tuỳ chọn):", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=3)
        self.pexels_var = tk.StringVar()
        tk.Entry(form, textvariable=self.pexels_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3, ipady=3
        )

        self.heal_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            cfg,
            text="Bật Codex AI Tự Sửa Lỗi (tự động dùng Codex CLI hoặc gọi Codex API dự phòng khi gặp lỗi)",
            variable=self.heal_var,
            bg=CARD, fg=YELLOW, selectcolor=BG, activebackground=CARD, activeforeground=YELLOW,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(6, 0))

        # --- TAB 2: Auto-Publish (Google / Facebook / YouTube) ---
        soc = tk.Frame(nb, bg=CARD, padx=16, pady=10)
        nb.add(soc, text="2. Tự động đăng bài (Google / Facebook / YouTube)")
        soc.columnconfigure(1, weight=1)

        tk.Label(soc, text="Link Google Sheet (sổ duyệt):", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.gs_url_var = tk.StringVar()
        tk.Entry(soc, textvariable=self.gs_url_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2, ipady=3
        )

        tk.Label(soc, text="File Google Key (.json):", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=2)
        self.gs_cred_var = tk.StringVar()
        tk.Entry(soc, textvariable=self.gs_cred_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=1, column=1, sticky="ew", padx=8, pady=2, ipady=3
        )
        tk.Button(soc, text="Chọn file...", command=self._pick_google_json, bg="#334155", fg=FG, relief="flat", padx=8, pady=2).grid(row=1, column=2, pady=2)

        tk.Label(soc, text="Link Google Drive (tuỳ chọn):", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=2)
        self.gd_url_var = tk.StringVar()
        tk.Entry(soc, textvariable=self.gd_url_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2, ipady=3
        )

        tk.Label(soc, text="Facebook Page ID:", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=2)
        self.fb_id_var = tk.StringVar()
        tk.Entry(soc, textvariable=self.fb_id_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=3, column=1, sticky="ew", padx=8, pady=2, ipady=3
        )
        self.fb_en_var = tk.BooleanVar(value=False)
        tk.Checkbutton(soc, text="Bật đăng FB", variable=self.fb_en_var, bg=CARD, fg=ACCENT, selectcolor=BG, activebackground=CARD, activeforeground=ACCENT).grid(row=3, column=2, sticky="w")

        tk.Label(soc, text="Facebook Page Access Token:", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", pady=2)
        self.fb_tok_var = tk.StringVar()
        tk.Entry(soc, textvariable=self.fb_tok_var, show="*", bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2, ipady=3
        )

        tk.Label(soc, text="Link kênh YouTube:", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", pady=2)
        self.yt_url_var = tk.StringVar()
        tk.Entry(soc, textvariable=self.yt_url_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(
            row=5, column=1, sticky="ew", padx=8, pady=2, ipady=3
        )
        self.yt_en_var = tk.BooleanVar(value=False)
        tk.Checkbutton(soc, text="Bật đăng YT", variable=self.yt_en_var, bg=CARD, fg=ACCENT, selectcolor=BG, activebackground=CARD, activeforeground=ACCENT).grid(row=5, column=2, sticky="w")

        tk.Label(soc, text="YouTube Client ID / Secret:", bg=CARD, fg=FG, font=("Segoe UI", 9)).grid(row=6, column=0, sticky="w", pady=2)
        yt_pair = tk.Frame(soc, bg=CARD)
        yt_pair.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2)
        yt_pair.columnconfigure(0, weight=1)
        yt_pair.columnconfigure(1, weight=1)
        self.yt_cid_var = tk.StringVar()
        self.yt_csec_var = tk.StringVar()
        tk.Entry(yt_pair, textvariable=self.yt_cid_var, bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=3)
        tk.Entry(yt_pair, textvariable=self.yt_csec_var, show="*", bg=BG, fg=FG, insertbackground=FG, relief="flat", font=("Consolas", 9)).grid(row=0, column=1, sticky="ew", ipady=3)

        # Progress Checklist Card
        prog = tk.Frame(self, bg=CARD, padx=16, pady=12)
        prog.pack(fill="x", padx=18, pady=(0, 10))
        tk.Label(prog, text="Tiến độ cài đặt từng bước", font=("Segoe UI", 10, "bold"), bg=CARD, fg=FG).pack(anchor="w", pady=(0, 6))

        self.pbar = ttk.Progressbar(prog, mode="determinate", maximum=len(STEPS))
        self.pbar.pack(fill="x", pady=(0, 8))

        for i, title in enumerate(STEPS):
            row = tk.Frame(prog, bg=CARD)
            row.pack(fill="x", pady=2)
            ic = tk.Label(row, text="⏳", font=("Segoe UI", 10), bg=CARD, fg=MUTED, width=3)
            ic.pack(side="left")
            tk.Label(row, text=f"{i + 1}. {title}", font=("Segoe UI", 9, "bold"), bg=CARD, fg=FG).pack(side="left")
            det = tk.Label(row, text="Chờ", font=("Segoe UI", 9), bg=CARD, fg=MUTED)
            det.pack(side="right")
            self.step_labels.append(ic)
            self.step_details.append(det)

        # Action Buttons
        btns = tk.Frame(self, bg=BG, padx=18, pady=4)
        btns.pack(fill="x")
        self.start_btn = tk.Button(
            btns, text="🚀 Bắt đầu cài đặt", command=self._start_install,
            bg="#0284c7", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", padx=18, pady=7
        )
        self.start_btn.pack(side="left")

        self.heal_btn = tk.Button(
            btns, text="🛠️ Gọi Codex tự sửa lỗi", command=self._manual_heal,
            bg="#b45309", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=7
        )
        self.heal_btn.pack(side="left", padx=10)

        self.rollback_btn = tk.Button(
            btns, text="↩️ Hoàn tác (Khôi phục backup)", command=self._rollback,
            bg="#475569", fg="white", font=("Segoe UI", 9), relief="flat", padx=12, pady=7
        )
        self.rollback_btn.pack(side="right")

        # Live Log Box
        log_frame = tk.Frame(self, bg=BG, padx=18, pady=8)
        log_frame.pack(fill="both", expand=True)
        tk.Label(log_frame, text="Nhật ký chi tiết (Live Log):", font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(anchor="w")
        self.log_box = scrolledtext.ScrolledText(
            log_frame, bg="#020617", fg="#e2e8f0", font=("Consolas", 9), relief="flat", height=10
        )
        self.log_box.pack(fill="both", expand=True, pady=(4, 0))

    def _populate_detected(self):
        if self.env.found:
            cx_txt = "Có Codex CLI" if self.env.codex_cmd else "Dùng Codex API"
            self.banner_lbl.config(
                text=f"✅ Đã phát hiện OpenClaw tại: {self.env.state_dir}  |  {cx_txt}  |  Agents: {', '.join(self.env.existing_agents) or 'main'}",
                fg=GREEN,
            )
            if self.env.existing_owners:
                self.owner_var.set(", ".join(self.env.existing_owners))
            if self.env.existing_api_key:
                self.api_var.set(self.env.existing_api_key)
                self._append_log("Đã tự nhận API Key có sẵn từ member-provider.secret.")
        else:
            self.banner_lbl.config(
                text="⚠️ Chưa phát hiện OpenClaw trên máy này. Vui lòng cài OpenClaw trước khi chạy bộ cài này.",
                fg=RED,
            )

    def _pick_google_json(self):
        path = filedialog.askopenfilename(title="Chọn file Google Service Account JSON", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            self.gs_cred_var.set(path)

    def _toggle_mode(self):
        state = "normal" if self.mode_var.get() == "separate_bot" else "disabled"
        self.token_entry.config(state=state)
        self.check_tok_btn.config(state=state)

    def _append_log(self, msg: str):
        def _do():
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
        self.after(0, _do)

    def _set_step(self, idx: int, state: str, detail: str):
        def _do():
            icon, color = ICONS.get(state, ("⏳", MUTED))
            self.step_labels[idx].config(text=icon, fg=color)
            self.step_details[idx].config(text=detail, fg=color)
            done_count = sum(1 for lbl in self.step_labels if lbl.cget("text") == "✅")
            self.pbar["value"] = done_count
        self.after(0, _do)

    def _check_token(self):
        tok = self.token_var.get().strip()
        if not tok:
            messagebox.showwarning("Thiếu token", "Vui lòng dán Telegram Bot Token trước.")
            return
        self._append_log("Đang kiểm tra Telegram Bot Token...")
        def worker():
            res = verify_telegram_token(tok)
            if res.get("ok"):
                msg = f"✅ Token hợp lệ! Bot: @{res['username']} ({res['first_name']})"
                self._append_log(msg)
                self.after(0, lambda: messagebox.showinfo("Hợp lệ", msg))
            else:
                msg = f"❌ Token không hợp lệ: {res.get('error')}"
                self._append_log(msg)
                self.after(0, lambda: messagebox.showerror("Lỗi Token", msg))
        threading.Thread(target=worker, daemon=True).start()

    def _start_install(self):
        if self.installing:
            return
        if not self.env.found:
            messagebox.showerror("Không thấy OpenClaw", "Không tìm thấy OpenClaw đang cài trên máy này.")
            return
        mode = self.mode_var.get()
        if mode == "separate_bot" and not self.token_var.get().strip():
            messagebox.showwarning("Thiếu Bot Token", "Vui lòng nhập Telegram Bot Token (hoặc chuyển sang chế độ gắn vào Bot đang có).")
            return

        self.installing = True
        self.start_btn.config(state="disabled", text="⏳ Đang cài đặt...")
        for i in range(len(STEPS)):
            self._set_step(i, "pending", "Chờ")

        owners = [x.strip() for x in self.owner_var.get().replace(";", ",").split(",") if x.strip()]
        opts = InstallOptions(
            env=self.env,
            mode=mode,
            bot_token=self.token_var.get().strip(),
            owner_ids=owners,
            api_key=self.api_var.get().strip(),
            pexels_key=self.pexels_var.get().strip(),
            enable_codex_heal=self.heal_var.get(),
            google_sheet_url=self.gs_url_var.get().strip(),
            google_cred_json=self.gs_cred_var.get().strip(),
            google_drive_url=self.gd_url_var.get().strip(),
            fb_page_id=self.fb_id_var.get().strip(),
            fb_page_token=self.fb_tok_var.get().strip(),
            fb_enabled=self.fb_en_var.get(),
            yt_channel_url=self.yt_url_var.get().strip(),
            yt_client_id=self.yt_cid_var.get().strip(),
            yt_client_secret=self.yt_csec_var.get().strip(),
            yt_enabled=self.yt_en_var.get(),
        )

        def worker():
            ok = run_install(opts, self._set_step, self._append_log)
            def finish():
                self.installing = False
                self.start_btn.config(state="normal", text="🚀 Bắt đầu cài đặt")
                if ok:
                    messagebox.showinfo(
                        "Cài đặt hoàn tất!",
                        "Đã cài xong OpenClaw Video Factory!\n\nBây giờ anh/chị có thể mở Telegram nhắn cho bot để tạo video 9:16 ngay.",
                    )
                else:
                    messagebox.showerror(
                        "Có lỗi xảy ra",
                        "Quá trình cài đặt gặp lỗi. Xem chi tiết ở khung Nhật ký hoặc bấm 'Gọi Codex tự sửa lỗi'.",
                    )
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _manual_heal(self):
        if not self.env.found:
            return
        log_text = self.log_box.get("1.0", "end").strip()
        if not log_text:
            messagebox.showinfo("Chưa có log lỗi", "Chưa có nhật ký lỗi để Codex phân tích.")
            return
        self._append_log("\n=== Gọi Codex tự chẩn đoán & sửa lỗi theo yêu cầu ===")
        def worker():
            ok, msg = auto_heal(
                self.env.codex_cmd,
                self.api_var.get().strip(),
                "Chẩn đoán thủ công",
                log_text,
                self.env.state_dir,
                [self.token_var.get().strip(), self.api_var.get().strip(), self.pexels_var.get().strip()],
                self._append_log,
            )
            self.after(0, lambda: messagebox.showinfo("Kết quả Codex", f"{'Thành công' if ok else 'Chưa sửa được'}: {msg[:300]}"))
        threading.Thread(target=worker, daemon=True).start()

    def _rollback(self):
        if not self.env.found:
            return
        if not messagebox.askyesno("Xác nhận hoàn tác", "Khôi phục openclaw.json về bản sao lưu gần nhất trước khi cài?"):
            return
        ok, msg = restore_latest_backup(Path(self.env.state_dir))
        self._append_log(f"↩️ {msg}")
        messagebox.showinfo("Hoàn tác", msg)


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
