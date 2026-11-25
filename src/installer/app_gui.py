# -*- coding: utf-8 -*-
"""Modern Light 2-Column Visual Installer for OpenClaw Video Factory (inspired by installer_emtroly)."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from codex_healer import auto_heal
from install_engine import InstallOptions, STEPS, run_install
from openclaw_detect import detect_installed_modules, detect_openclaw, verify_api_key, verify_telegram_token
from openclaw_merge import restore_latest_backup

APP_VERSION = "v25.11.2026"

# Clean light palette matching installer_emtroly
BG_CANVAS = "#F1F5F9"
BG_CARD = "#FFFFFF"
BG_SUBTLE = "#F8FAFC"
BG_INFO = "#EFF6FF"
BG_SUCCESS = "#ECFDF5"
BG_WARN = "#FFFBEB"
BG_DANGER = "#FEF2F2"
BORDER = "#E2E8F0"
BORDER_INFO = "#BFDBFE"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
SUCCESS = "#059669"
WARN = "#D97706"
DANGER = "#DC2626"
TEXT_MAIN = "#0F172A"
TEXT_SUB = "#64748B"

STEP_BADGES = {
    "pending": ("●", "#CBD5E1", TEXT_SUB, "Chờ thực hiện"),
    "running": ("▶", PRIMARY, PRIMARY, "Đang chạy..."),
    "healing": ("🛠", WARN, WARN, "Codex đang tự sửa..."),
    "done": ("✓", SUCCESS, SUCCESS, "Hoàn tất"),
    "skipped": ("⏭", TEXT_SUB, TEXT_SUB, "Bỏ qua"),
    "error": ("✕", DANGER, DANGER, "Gặp lỗi"),
}


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"OpenClaw Video Factory {APP_VERSION} — Cài đặt Tạo Video 9:16")
        self.geometry("1080x780")
        self.minsize(980, 700)
        self.configure(bg=BG_CANVAS)

        self.env = detect_openclaw()
        self.installing = False
        self.step_widgets = []

        self._build_ui()
        self._populate_detected()

    def _card(self, parent, pad=16):
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        inner = tk.Frame(outer, bg=BG_CARD, padx=pad, pady=pad)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _entry(self, parent, var, show="", width=None):
        wrap = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        kw = dict(textvariable=var, bg=BG_SUBTLE, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
                  relief="flat", font=("Segoe UI", 9.5))
        if show:
            kw["show"] = show
        if width:
            kw["width"] = width
        e = tk.Entry(wrap, **kw)
        e.pack(fill="both", expand=True, ipady=5, padx=6)
        return wrap, e

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#E2E8F0", background=PRIMARY, thickness=8, borderwidth=0)
        style.configure("TNotebook", background=BG_CANVAS, borderwidth=0)
        style.configure("TNotebook.Tab", background="#E2E8F0", foreground=TEXT_SUB, padding=(16, 8), font=("Segoe UI", 9.5, "bold"))
        style.map("TNotebook.Tab", background=[("selected", BG_CARD)], foreground=[("selected", PRIMARY)])

        # Top Header Bar
        topbar = tk.Frame(self, bg=BG_CARD, padx=22, pady=14)
        topbar.pack(fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        title_row = tk.Frame(topbar, bg=BG_CARD)
        title_row.pack(fill="x")
        tk.Label(title_row, text="🎬 OpenClaw Video Factory", font=("Segoe UI", 16, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(side="left")
        tk.Label(title_row, text=f"  {APP_VERSION}", font=("Segoe UI", 10, "bold"), bg=BG_INFO, fg=PRIMARY, padx=8, pady=2).pack(side="left", padx=(10, 0))
        tk.Label(topbar, text="Cài đặt tính năng tạo video dọc 9:16 + tự động đăng bài vào OpenClaw đang chạy trên máy",
                 font=("Segoe UI", 9.5), bg=BG_CARD, fg=TEXT_SUB).pack(anchor="w", pady=(3, 0))

        # Main 2-Column Body
        body = tk.Frame(self, bg=BG_CANVAS, padx=18, pady=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=310)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # LEFT COLUMN: Status + 7-Step Visual Stepper
        left = tk.Frame(body, bg=BG_CANVAS)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        # OpenClaw Detection Card
        det_outer, det = self._card(left, pad=12)
        det_outer.pack(fill="x", pady=(0, 10))
        tk.Label(det, text="Trạng thái OpenClaw trên máy", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w")
        self.det_badge = tk.Label(det, text="Đang kiểm tra...", font=("Segoe UI", 9, "bold"), bg=BG_INFO, fg=PRIMARY, padx=8, pady=4, anchor="w", justify="left", wraplength=260)
        self.det_badge.pack(fill="x", pady=(6, 4))
        self.det_meta = tk.Label(det, text="", font=("Segoe UI", 8.5), bg=BG_CARD, fg=TEXT_SUB, anchor="w", justify="left", wraplength=260)
        self.det_meta.pack(fill="x")

        # Modular Selection Card (Cài từng phần + trạng thái Đã cài / Chưa cài)
        mod_outer, mod = self._card(left, pad=12)
        mod_outer.pack(fill="x", pady=(0, 10))
        tk.Label(mod, text="Chọn phần muốn cài (Cài từng phần)", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w", pady=(0, 6))
        self.mod_video_var = tk.BooleanVar(value=True)
        self.mod_google_var = tk.BooleanVar(value=False)
        self.mod_fb_var = tk.BooleanVar(value=False)
        self.mod_yt_var = tk.BooleanVar(value=False)
        self.mod_badges = {}
        for key, var, label in [
            ("video", self.mod_video_var, "🎬 Tạo Video 9:16"),
            ("google", self.mod_google_var, "📊 Google Sheet & Drive"),
            ("facebook", self.mod_fb_var, "📘 Đăng Facebook"),
            ("youtube", self.mod_yt_var, "▶️ Đăng YouTube"),
        ]:
            mrow = tk.Frame(mod, bg=BG_CARD)
            mrow.pack(fill="x", pady=2)
            tk.Checkbutton(mrow, text=label, variable=var, bg=BG_CARD, fg=TEXT_MAIN, activebackground=BG_CARD,
                           font=("Segoe UI", 9), command=self._refresh_modular_ui).pack(side="left")
            badge = tk.Label(mrow, text="Chưa cài", font=("Segoe UI", 8, "bold"), bg=BG_SUBTLE, fg=TEXT_SUB, padx=7, pady=1)
            badge.pack(side="right")
            self.mod_badges[key] = badge

        # 7-Step Progress Stepper Card
        st_outer, st = self._card(left, pad=12)
        st_outer.pack(fill="both", expand=True)
        tk.Label(st, text="Tiến độ cài đặt (7 bước)", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w")
        self.pct_lbl = tk.Label(st, text="0 / 7 bước hoàn tất", font=("Segoe UI", 8.5), bg=BG_CARD, fg=TEXT_SUB)
        self.pct_lbl.pack(anchor="w", pady=(2, 6))
        self.pbar = ttk.Progressbar(st, mode="determinate", maximum=len(STEPS))
        self.pbar.pack(fill="x", pady=(0, 12))

        for i, title in enumerate(STEPS):
            item = tk.Frame(st, bg=BG_SUBTLE, padx=10, pady=7)
            item.pack(fill="x", pady=3)
            dot = tk.Label(item, text="●", font=("Segoe UI", 10, "bold"), bg=BG_SUBTLE, fg="#CBD5E1", width=2)
            dot.pack(side="left", anchor="n")
            txt_col = tk.Frame(item, bg=BG_SUBTLE)
            txt_col.pack(side="left", fill="x", expand=True)
            t_lbl = tk.Label(txt_col, text=f"Bước {i + 1}: {title}", font=("Segoe UI", 9, "bold"), bg=BG_SUBTLE, fg=TEXT_MAIN, anchor="w", wraplength=220, justify="left")
            t_lbl.pack(anchor="w")
            d_lbl = tk.Label(txt_col, text="Chờ thực hiện", font=("Segoe UI", 8), bg=BG_SUBTLE, fg=TEXT_SUB, anchor="w")
            d_lbl.pack(anchor="w")
            self.step_widgets.append((item, dot, t_lbl, d_lbl))

        # RIGHT COLUMN: Tabs (Config + Social) + Buttons + Live Log
        right = tk.Frame(body, bg=BG_CANVAS)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        nb = ttk.Notebook(right)
        nb.grid(row=0, column=0, sticky="ew")

        # --- TAB 1: OpenClaw & API Key cá nhân ---
        t1 = tk.Frame(nb, bg=BG_CARD, padx=18, pady=14)
        nb.add(t1, text="  1. Kết nối OpenClaw & API Key  ")
        t1.columnconfigure(1, weight=1)

        # Mode radio
        m_row = tk.Frame(t1, bg=BG_INFO, padx=12, pady=8)
        m_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        tk.Label(m_row, text="Chế độ cài:", font=("Segoe UI", 9.5, "bold"), bg=BG_INFO, fg=TEXT_MAIN).pack(side="left")
        self.mode_var = tk.StringVar(value="separate_bot")
        tk.Radiobutton(m_row, text="Tạo Bot Video riêng (Khuyên dùng)", variable=self.mode_var, value="separate_bot",
                       bg=BG_INFO, fg=TEXT_MAIN, activebackground=BG_INFO, command=self._toggle_mode).pack(side="left", padx=(12, 16))
        tk.Radiobutton(m_row, text="Gắn vào Bot hiện có", variable=self.mode_var, value="existing_bot",
                       bg=BG_INFO, fg=TEXT_MAIN, activebackground=BG_INFO, command=self._toggle_mode).pack(side="left")

        # Telegram Bot Token
        tk.Label(t1, text="Telegram Bot Token:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9.5, "bold")).grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.token_var = tk.StringVar()
        tok_wrap, self.token_entry = self._entry(t1, self.token_var)
        tok_wrap.grid(row=1, column=1, sticky="ew", padx=8, pady=(4, 2))
        self.check_tok_btn = tk.Button(t1, text="Kiểm tra Bot", command=self._check_token, bg=BG_SUBTLE, fg=TEXT_MAIN,
                                       relief="solid", bd=1, font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2")
        self.check_tok_btn.grid(row=1, column=2, pady=(4, 2))

        # Telegram Owner ID
        tk.Label(t1, text="Telegram ID chủ máy:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9.5, "bold")).grid(row=2, column=0, sticky="w", pady=4)
        self.owner_var = tk.StringVar()
        own_wrap, _ = self._entry(t1, self.owner_var)
        own_wrap.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        # Personal API Key (with Show/Hide + Verify + Use Existing)
        tk.Label(t1, text="API Key cá nhân (Ảnh AI + Codex):", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9.5, "bold")).grid(row=3, column=0, sticky="w", pady=(6, 2))
        self.api_var = tk.StringVar()
        api_wrap, self.api_entry = self._entry(t1, self.api_var, show="*")
        api_wrap.grid(row=3, column=1, sticky="ew", padx=8, pady=(6, 2))
        api_btns = tk.Frame(t1, bg=BG_CARD)
        api_btns.grid(row=3, column=2, pady=(6, 2))
        self.show_api = False
        self.toggle_api_btn = tk.Button(api_btns, text="Hiện", command=self._toggle_api_vis, bg=BG_SUBTLE, fg=TEXT_MAIN, relief="solid", bd=1, font=("Segoe UI", 8.5), padx=7, pady=4, cursor="hand2")
        self.toggle_api_btn.pack(side="left", padx=(0, 4))
        tk.Button(api_btns, text="Kiểm tra Key", command=self._check_api, bg=BG_SUBTLE, fg=PRIMARY, relief="solid", bd=1, font=("Segoe UI", 8.5, "bold"), padx=8, pady=4, cursor="hand2").pack(side="left")

        api_hint_row = tk.Frame(t1, bg=BG_CARD)
        api_hint_row.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(0, 4))
        tk.Label(api_hint_row, text="Mỗi khách nhập API Key riêng của mình (dùng tạo ảnh AI & Codex tự sửa lỗi).", font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_SUB).pack(side="left")
        self.use_existing_api_btn = tk.Button(api_hint_row, text="Lấy key sẵn từ OpenClaw", command=self._load_existing_api,
                                              bg=BG_INFO, fg=PRIMARY, relief="flat", font=("Segoe UI", 8, "bold"), padx=6, pady=1, cursor="hand2")

        # Pexels Key
        tk.Label(t1, text="Pexels API Key (tuỳ chọn):", bg=BG_CARD, fg=TEXT_SUB, font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", pady=4)
        self.pexels_var = tk.StringVar()
        px_wrap, _ = self._entry(t1, self.pexels_var)
        px_wrap.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        # Codex Self-Heal Checkbox
        self.heal_var = tk.BooleanVar(value=True)
        heal_box = tk.Frame(t1, bg=BG_WARN, padx=10, pady=6)
        heal_box.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        tk.Checkbutton(
            heal_box,
            text="Bật Codex AI Tự Sửa Lỗi (tự dùng Codex CLI hoặc API Key ở trên để tự sửa nếu gặp lỗi cài đặt)",
            variable=self.heal_var, bg=BG_WARN, fg="#92400E", activebackground=BG_WARN,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        # --- TAB 2: Tự động đăng bài (chỉ hiện các phần đã tích chọn bên trái) ---
        t2 = tk.Frame(nb, bg=BG_CARD, padx=18, pady=12)
        nb.add(t2, text="  2. Tự động đăng bài (Tuỳ chọn)  ")

        self.soc_empty_lbl = tk.Label(
            t2,
            text="Khách chưa chọn module đăng bài nào (Google Sheet / Facebook / YouTube).\n\nTích chọn ở mục 'Chọn phần muốn cài' bên cột trái nếu muốn cấu hình thêm kênh đăng bài, hoặc bỏ qua nếu chỉ cần chức năng Tạo Video 9:16.",
            font=("Segoe UI", 9.5), bg=BG_SUBTLE, fg=TEXT_SUB, padx=16, pady=24, justify="left", wraplength=600,
        )

        # Google Section Frame
        self.google_frame = tk.LabelFrame(t2, text=" Google Sheet & Google Drive ", bg=BG_CARD, fg=PRIMARY, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        self.google_frame.columnconfigure(1, weight=1)
        tk.Label(self.google_frame, text="Link Google Sheet:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.gs_url_var = tk.StringVar()
        w, _ = self._entry(self.google_frame, self.gs_url_var)
        w.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(self.google_frame, text="File Google Key (.json):", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=2)
        self.gs_cred_var = tk.StringVar()
        w, _ = self._entry(self.google_frame, self.gs_cred_var)
        w.grid(row=1, column=1, sticky="ew", padx=8, pady=2)
        tk.Button(self.google_frame, text="Chọn file...", command=self._pick_google_json, bg=BG_SUBTLE, fg=TEXT_MAIN, relief="solid", bd=1, font=("Segoe UI", 8.5), padx=10, pady=3, cursor="hand2").grid(row=1, column=2, pady=2)
        tk.Label(self.google_frame, text="Link Google Drive:", bg=BG_CARD, fg=TEXT_SUB, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=2)
        self.gd_url_var = tk.StringVar()
        w, _ = self._entry(self.google_frame, self.gd_url_var)
        w.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2)

        # Facebook Section Frame
        self.fb_frame = tk.LabelFrame(t2, text=" Facebook Fanpage ", bg=BG_CARD, fg=PRIMARY, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        self.fb_frame.columnconfigure(1, weight=1)
        tk.Label(self.fb_frame, text="Facebook Page ID:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.fb_id_var = tk.StringVar()
        w, _ = self._entry(self.fb_frame, self.fb_id_var)
        w.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(self.fb_frame, text="Page Access Token:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=2)
        self.fb_tok_var = tk.StringVar()
        w, _ = self._entry(self.fb_frame, self.fb_tok_var, show="*")
        w.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        self.fb_en_var = self.mod_fb_var

        # YouTube Section Frame
        self.yt_frame = tk.LabelFrame(t2, text=" YouTube Shorts ", bg=BG_CARD, fg=PRIMARY, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        self.yt_frame.columnconfigure(1, weight=1)
        tk.Label(self.yt_frame, text="Link kênh YouTube:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.yt_url_var = tk.StringVar()
        w, _ = self._entry(self.yt_frame, self.yt_url_var)
        w.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(self.yt_frame, text="Client ID / Secret:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=2)
        yt_box = tk.Frame(self.yt_frame, bg=BG_CARD)
        yt_box.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        yt_box.columnconfigure(0, weight=1)
        yt_box.columnconfigure(1, weight=1)
        self.yt_cid_var = tk.StringVar()
        self.yt_csec_var = tk.StringVar()
        w1, _ = self._entry(yt_box, self.yt_cid_var)
        w2, _ = self._entry(yt_box, self.yt_csec_var, show="*")
        w1.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        w2.grid(row=0, column=1, sticky="ew")
        self.yt_en_var = self.mod_yt_var

        self._refresh_modular_ui()

        # Action Bar
        act = tk.Frame(right, bg=BG_CANVAS, pady=10)
        act.grid(row=1, column=0, sticky="ew")
        self.start_btn = tk.Button(act, text="🚀 Bắt đầu cài đặt ngay", command=self._start_install,
                                   bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK, activeforeground="white",
                                   font=("Segoe UI", 10, "bold"), relief="flat", padx=20, pady=9, cursor="hand2")
        self.start_btn.pack(side="left")
        tk.Button(act, text="🛠️ Gọi Codex tự sửa lỗi", command=self._manual_heal,
                  bg="#FFFBEB", fg="#B45309", relief="solid", bd=1, font=("Segoe UI", 9.5, "bold"), padx=14, pady=8, cursor="hand2").pack(side="left", padx=10)
        tk.Button(act, text="↩️ Hoàn tác backup", command=self._rollback,
                  bg=BG_CARD, fg=TEXT_MAIN, relief="solid", bd=1, font=("Segoe UI", 9), padx=12, pady=8, cursor="hand2").pack(side="right")

        # Live Log Card
        log_outer, log_inner = self._card(right, pad=12)
        log_outer.grid(row=2, column=0, sticky="nsew")
        tk.Label(log_inner, text="Nhật ký cài đặt trực tiếp (Live Log)", font=("Segoe UI", 9.5, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w", pady=(0, 6))
        self.log_box = scrolledtext.ScrolledText(log_inner, bg="#0F172A", fg="#E2E8F0", font=("Consolas", 9), relief="flat", height=11)
        self.log_box.pack(fill="both", expand=True)

    def _populate_detected(self):
        if self.env.found:
            self.det_badge.config(text="✅ Đã tìm thấy OpenClaw đang cài", bg=BG_SUCCESS, fg=SUCCESS)
            cx = "Có sẵn Codex CLI" if self.env.codex_cmd else "Dùng Codex API dự phòng"
            self.det_meta.config(text=f"Thư mục: {self.env.state_dir}\nAgent hiện có: {', '.join(self.env.existing_agents) or 'main'}\nTự sửa lỗi: {cx}")
            if self.env.existing_owners:
                self.owner_var.set(", ".join(self.env.existing_owners))
            if self.env.existing_api_key:
                self.use_existing_api_btn.pack(side="right")
                self._append_log("Phát hiện OpenClaw đã có sẵn API key — khách có thể nhập key riêng hoặc bấm 'Lấy key sẵn từ OpenClaw'.")
            self._refresh_installed_badges(prefill=True)
        else:
            self.det_badge.config(text="⚠️ Không tìm thấy OpenClaw trên máy", bg=BG_DANGER, fg=DANGER)
            self.det_meta.config(text="Vui lòng cài đặt OpenClaw trước khi chạy bộ cài tạo video này.")

    def _refresh_installed_badges(self, prefill: bool = False):
        if not self.env.found:
            return
        st = detect_installed_modules(self.env.state_dir)
        for key, badge in self.mod_badges.items():
            if st.get(key):
                badge.config(text="✓ Đã cài", bg=BG_SUCCESS, fg=SUCCESS)
            else:
                badge.config(text="Chưa cài", bg=BG_SUBTLE, fg=TEXT_SUB)
        if prefill:
            cfg = st.get("social_cfg") or {}
            gs = cfg.get("google_sheet") or {}
            gd = cfg.get("google_drive") or {}
            fb = cfg.get("facebook") or {}
            yt = cfg.get("youtube") or {}
            if gs.get("url") and not self.gs_url_var.get():
                self.gs_url_var.set(gs["url"])
            if gd.get("folder_url") and not self.gd_url_var.get():
                self.gd_url_var.set(gd["folder_url"])
            if fb.get("page_id") and not self.fb_id_var.get():
                self.fb_id_var.set(fb["page_id"])
            if yt.get("channel_url") and not self.yt_url_var.get():
                self.yt_url_var.set(yt["channel_url"])

    def _load_existing_api(self):
        if self.env.existing_api_key:
            self.api_var.set(self.env.existing_api_key)
            self._append_log("Đã điền API Key từ cấu hình OpenClaw hiện tại.")

    def _toggle_api_vis(self):
        self.show_api = not self.show_api
        self.api_entry.config(show="" if self.show_api else "*")
        self.toggle_api_btn.config(text="Ẩn" if self.show_api else "Hiện")

    def _pick_google_json(self):
        p = filedialog.askopenfilename(title="Chọn file Google Service Account JSON", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p:
            self.gs_cred_var.set(p)

    def _refresh_modular_ui(self):
        for f in (self.soc_empty_lbl, self.google_frame, self.fb_frame, self.yt_frame):
            f.pack_forget()
        any_soc = False
        if self.mod_google_var.get():
            self.google_frame.pack(fill="x", pady=(0, 6))
            any_soc = True
        if self.mod_fb_var.get():
            self.fb_frame.pack(fill="x", pady=(0, 6))
            any_soc = True
        if self.mod_yt_var.get():
            self.yt_frame.pack(fill="x", pady=(0, 6))
            any_soc = True
        if not any_soc:
            self.soc_empty_lbl.pack(fill="x", pady=10)

    def _toggle_mode(self):
        state = "normal" if self.mode_var.get() == "separate_bot" else "disabled"
        self.token_entry.config(state=state)
        self.check_tok_btn.config(state=state)

    def _append_log(self, msg: str):
        self.after(0, lambda: (self.log_box.insert("end", msg + "\n"), self.log_box.see("end")))

    def _set_step(self, idx: int, state: str, detail: str):
        def _do():
            icon, dot_fg, text_fg, default_txt = STEP_BADGES.get(state, STEP_BADGES["pending"])
            item, dot, t_lbl, d_lbl = self.step_widgets[idx]
            bg = BG_SUCCESS if state == "done" else (BG_INFO if state == "running" else (BG_WARN if state == "healing" else (BG_DANGER if state == "error" else BG_SUBTLE)))
            for w in (item, dot, t_lbl, d_lbl, t_lbl.master):
                w.config(bg=bg)
            dot.config(text=icon, fg=dot_fg)
            d_lbl.config(text=detail or default_txt, fg=text_fg)
            done_count = sum(1 for _, d, _, _ in self.step_widgets if d.cget("text") == "✓")
            self.pbar["value"] = done_count
            self.pct_lbl.config(text=f"{done_count} / {len(STEPS)} bước hoàn tất")
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

    def _check_api(self):
        key = self.api_var.get().strip()
        if not key:
            messagebox.showwarning("Thiếu API Key", "Vui lòng nhập API Key cá nhân trước.")
            return
        self._append_log("Đang kiểm tra API Key cá nhân...")
        def worker():
            res = verify_api_key(key)
            if res.get("ok"):
                msg = f"✅ API Key hợp lệ! Kết nối thành công ({res['count']} model khả dụng)."
                self._append_log(msg)
                self.after(0, lambda: messagebox.showinfo("API Key hợp lệ", msg))
            else:
                msg = f"❌ API Key không hợp lệ hoặc không kết nối được: {res.get('error')}"
                self._append_log(msg)
                self.after(0, lambda: messagebox.showerror("Lỗi API Key", msg))
        threading.Thread(target=worker, daemon=True).start()

    def _start_install(self):
        if self.installing:
            return
        if not self.env.found:
            messagebox.showerror("Không thấy OpenClaw", "Không tìm thấy OpenClaw đang cài trên máy này.")
            return
        if not any([self.mod_video_var.get(), self.mod_google_var.get(), self.mod_fb_var.get(), self.mod_yt_var.get()]):
            messagebox.showwarning("Chưa chọn module", "Vui lòng tích chọn ít nhất 1 phần muốn cài ở cột bên trái.")
            return
        mode = self.mode_var.get()
        if self.mod_video_var.get() and mode == "separate_bot" and not self.token_var.get().strip():
            messagebox.showwarning("Thiếu Bot Token", "Vui lòng nhập Telegram Bot Token (hoặc chọn 'Gắn vào Bot hiện có').")
            return
        if self.mod_video_var.get() and not self.api_var.get().strip():
            messagebox.showwarning("Thiếu API Key", "Vui lòng nhập API Key cá nhân (hoặc bấm 'Lấy key sẵn từ OpenClaw').")
            return

        self.installing = True
        self.start_btn.config(state="disabled", text="⏳ Đang cài đặt...")
        for i in range(len(STEPS)):
            self._set_step(i, "pending", "Chờ thực hiện")

        owners = [x.strip() for x in self.owner_var.get().replace(";", ",").split(",") if x.strip()]
        opts = InstallOptions(
            env=self.env,
            mode=mode,
            bot_token=self.token_var.get().strip(),
            owner_ids=owners,
            api_key=self.api_var.get().strip(),
            pexels_key=self.pexels_var.get().strip(),
            enable_codex_heal=self.heal_var.get(),
            install_video_core=self.mod_video_var.get(),
            install_google=self.mod_google_var.get(),
            install_facebook=self.mod_fb_var.get(),
            install_youtube=self.mod_yt_var.get(),
            google_sheet_url=self.gs_url_var.get().strip(),
            google_cred_json=self.gs_cred_var.get().strip(),
            google_drive_url=self.gd_url_var.get().strip(),
            fb_page_id=self.fb_id_var.get().strip(),
            fb_page_token=self.fb_tok_var.get().strip(),
            fb_enabled=self.mod_fb_var.get(),
            yt_channel_url=self.yt_url_var.get().strip(),
            yt_client_id=self.yt_cid_var.get().strip(),
            yt_client_secret=self.yt_csec_var.get().strip(),
            yt_enabled=self.mod_yt_var.get(),
        )

        def worker():
            ok = run_install(opts, self._set_step, self._append_log)
            def finish():
                self.installing = False
                self.start_btn.config(state="normal", text="🚀 Bắt đầu cài đặt ngay")
                self._refresh_installed_badges(prefill=False)
                if ok:
                    messagebox.showinfo("Hoàn tất!", "Đã cài xong OpenClaw Video Factory!\n\nMở Telegram nhắn cho bot để tạo video 9:16 ngay.")
                else:
                    messagebox.showerror("Có lỗi xảy ra", "Cài đặt gặp lỗi. Xem khung Nhật ký hoặc bấm 'Gọi Codex tự sửa lỗi'.")
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _manual_heal(self):
        if not self.env.found:
            return
        log_text = self.log_box.get("1.0", "end").strip()
        if not log_text:
            messagebox.showinfo("Chưa có log lỗi", "Chưa có nhật ký lỗi để Codex phân tích.")
            return
        self._append_log("\n=== Gọi Codex tự chẩn đoán & sửa lỗi ===")
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
        if not messagebox.askyesno("Xác nhận hoàn tác", "Khôi phục openclaw.json về bản sao lưu gần nhất?"):
            return
        ok, msg = restore_latest_backup(Path(self.env.state_dir))
        self._append_log(f"↩️ {msg}")
        messagebox.showinfo("Hoàn tác", msg)


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
