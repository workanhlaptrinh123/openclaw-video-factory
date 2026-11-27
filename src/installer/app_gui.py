# -*- coding: utf-8 -*-
"""Executive Sidebar Multi-Page Windows Installer for OpenClaw Video Factory (modeled after installer_emtroly)."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from codex_healer import auto_heal
from install_engine import InstallOptions, STEPS, run_install
from oauth_connect import (
    connect_facebook_get_pages,
    connect_google_and_create_sheet,
    load_bundled_oauth_config,
)
from openclaw_detect import detect_installed_modules, detect_openclaw, verify_api_key, verify_telegram_token
from openclaw_merge import restore_latest_backup

APP_VERSION = "v27.11.2026.3"

# Executive Light Palette (matching installer_emtroly)
BG_CANVAS = "#F1F5F9"
BG_CARD = "#FFFFFF"
BG_SUBTLE = "#F8FAFC"
BG_INFO = "#EFF6FF"
BG_SUCCESS = "#ECFDF5"
BG_WARN = "#FFFBEB"
BG_DANGER = "#FEF2F2"
BORDER = "#E2E8F0"
BORDER_INPUT = "#CBD5E1"
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
        self.title(f"OpenClaw Video Factory {APP_VERSION} — Trình Cài Đặt")
        self.geometry("1080x760")
        self.minsize(980, 680)
        self.configure(bg=BG_CANVAS)

        self.env = detect_openclaw()
        self.installing = False
        self.current_page = "overview"
        self.pages = {}
        self.nav_buttons = {}
        self.step_widgets = []
        self.mod_badges = {}
        self.fb_pages = []
        self.show_api = False

        # Shared state vars
        self.mod_video_var = tk.BooleanVar(value=True)
        self.mod_google_var = tk.BooleanVar(value=False)
        self.mod_fb_var = tk.BooleanVar(value=False)
        self.mod_yt_var = tk.BooleanVar(value=False)

        self.mode_var = tk.StringVar(value="existing_bot")
        self.token_var = tk.StringVar()
        self.owner_var = tk.StringVar()
        self.api_var = tk.StringVar()
        self.pixabay_var = tk.StringVar()
        self.logo_en_var = tk.BooleanVar(value=False)
        self.logo_path_var = tk.StringVar()
        self.heal_var = tk.BooleanVar(value=True)

        self.gs_url_var = tk.StringVar()
        self.gs_cred_var = tk.StringVar()
        self.gd_url_var = tk.StringVar()
        self.fb_id_var = tk.StringVar()
        self.fb_tok_var = tk.StringVar()
        self.fb_picker_var = tk.StringVar()
        self.yt_url_var = tk.StringVar()
        self.yt_cid_var = tk.StringVar()
        self.yt_csec_var = tk.StringVar()

        self._build_ui()
        self._populate_detected()
        self._show_page("overview")

    # ---- Reusable clean widgets ----
    def _card(self, parent, pad=18):
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        inner = tk.Frame(outer, bg=BG_CARD, padx=pad, pady=pad)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _entry(self, parent, var, show="", width=36):
        wrap = tk.Frame(parent, bg="#FFFFFF", highlightbackground=BORDER_INPUT, highlightcolor=PRIMARY, highlightthickness=1)
        kw = dict(
            textvariable=var, bg="#FFFFFF", fg=TEXT_MAIN,
            disabledbackground="#F1F5F9", disabledforeground="#94A3B8",
            insertbackground=PRIMARY, relief="flat", bd=0, width=width, font=("Consolas", 10),
        )
        if show:
            kw["show"] = show
        e = tk.Entry(wrap, **kw)
        e.pack(fill="both", expand=True, ipady=6, padx=9)
        wrap.bind("<Button-1>", lambda _ev, ent=e: ent.focus_set())
        return wrap, e

    def _btn(self, parent, text, cmd, kind="secondary", pad_x=14, pad_y=7):
        if kind == "primary":
            return tk.Button(parent, text=text, command=cmd, bg=PRIMARY, fg="#FFFFFF",
                             activebackground=PRIMARY_DARK, activeforeground="#FFFFFF",
                             relief="flat", bd=0, font=("Segoe UI", 10, "bold"), padx=pad_x, pady=pad_y, cursor="hand2")
        if kind == "warn":
            return tk.Button(parent, text=text, command=cmd, bg=BG_WARN, fg="#92400E",
                             activebackground="#FEF3C7", activeforeground="#92400E",
                             relief="solid", bd=1, font=("Segoe UI", 9, "bold"), padx=pad_x, pady=pad_y, cursor="hand2")
        if kind == "info":
            return tk.Button(parent, text=text, command=cmd, bg=BG_INFO, fg=PRIMARY,
                             activebackground="#DBEAFE", activeforeground=PRIMARY_DARK,
                             relief="solid", bd=1, font=("Segoe UI", 9, "bold"), padx=pad_x, pady=pad_y, cursor="hand2")
        return tk.Button(parent, text=text, command=cmd, bg=BG_CARD, fg=TEXT_MAIN,
                         activebackground=BG_SUBTLE, activeforeground=TEXT_MAIN,
                         relief="solid", bd=1, font=("Segoe UI", 9), padx=pad_x, pady=pad_y, cursor="hand2")

    # ---- Master 2-pane Shell (Sidebar + Page Canvas) ----
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#DBEAFE", background=PRIMARY, thickness=10, borderwidth=0)

        root_grid = tk.Frame(self, bg=BG_CANVAS)
        root_grid.pack(fill="both", expand=True)
        root_grid.columnconfigure(0, weight=0, minsize=250)
        root_grid.columnconfigure(1, weight=1)
        root_grid.rowconfigure(0, weight=1)

        # ===== LEFT EXECUTIVE SIDEBAR =====
        sidebar_wrap = tk.Frame(root_grid, bg=BORDER, padx=0)
        sidebar_wrap.grid(row=0, column=0, sticky="nsew")
        sidebar = tk.Frame(sidebar_wrap, bg=BG_CARD, padx=14, pady=16)
        sidebar.pack(fill="both", expand=True, padx=(0, 1))

        # Brand Header Card
        b_out = tk.Frame(sidebar, bg=BORDER_INPUT, padx=1, pady=1)
        b_out.pack(fill="x", pady=(0, 16))
        b_top = tk.Frame(b_out, bg=BG_CARD, padx=12, pady=12)
        b_top.pack(fill="x")
        r1 = tk.Frame(b_top, bg=BG_CARD)
        r1.pack(fill="x")
        tk.Label(r1, text="🎬 Video Factory", font=("Segoe UI", 13, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(side="left")
        tk.Label(r1, text="SUITE", font=("Segoe UI", 8, "bold"), bg=BG_INFO, fg=PRIMARY, padx=6, pady=1).pack(side="right")
        tk.Frame(b_out, bg=BORDER, height=1).pack(fill="x")
        b_bot = tk.Frame(b_out, bg=BG_SUBTLE, padx=12, pady=7)
        b_bot.pack(fill="x")
        tk.Label(b_bot, text="9:16 · 16:9 · 1:1 · Auto-Post", font=("Segoe UI", 9), bg=BG_SUBTLE, fg=TEXT_SUB).pack(anchor="w")

        # Navigation Group
        tk.Label(sidebar, text="CÁC BƯỚC CÀI ĐẶT", font=("Segoe UI", 8, "bold"), bg=BG_CARD, fg="#94A3B8").pack(anchor="w", padx=8, pady=(0, 6))

        nav_items = [
            ("overview", "1. Tổng quan & Chọn phần"),
            ("video",    "2. Kết nối Bot & API Key"),
            ("social",   "3. Tự động đăng bài"),
            ("install",  "4. Tiến độ & Nhật ký"),
        ]
        for key, label in nav_items:
            btn = tk.Button(
                sidebar, text=f"  {label}", anchor="w", relief="flat", bd=0,
                font=("Segoe UI", 10), padx=10, pady=10, cursor="hand2",
                command=lambda k=key: self._show_page(k),
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # Spacer
        tk.Frame(sidebar, bg=BG_CARD).pack(fill="both", expand=True)

        # Bottom Status Card
        st_box = tk.Frame(sidebar, bg=BORDER, padx=1, pady=1)
        st_box.pack(fill="x", pady=(10, 0))
        st_in = tk.Frame(st_box, bg=BG_SUBTLE, padx=12, pady=10)
        st_in.pack(fill="x")
        self.sb_status_lbl = tk.Label(st_in, text="● Đang kiểm tra OpenClaw...", font=("Segoe UI", 9, "bold"), bg=BG_SUBTLE, fg=PRIMARY, anchor="w", wraplength=200, justify="left")
        self.sb_status_lbl.pack(fill="x")
        self.sb_meta_lbl = tk.Label(st_in, text=f"Phiên bản {APP_VERSION}", font=("Segoe UI", 8), bg=BG_SUBTLE, fg=TEXT_SUB, anchor="w")
        self.sb_meta_lbl.pack(fill="x", pady=(3, 0))

        # ===== RIGHT MAIN CONTENT AREA =====
        right = tk.Frame(root_grid, bg=BG_CANVAS)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.page_host = tk.Frame(right, bg=BG_CANVAS, padx=26, pady=22)
        self.page_host.grid(row=0, column=0, sticky="nsew")
        self.page_host.rowconfigure(0, weight=1)
        self.page_host.columnconfigure(0, weight=1)

        # Build all 4 clean separate screens
        self._build_page_overview()
        self._build_page_video()
        self._build_page_social()
        self._build_page_install()

        # Bottom Footer Navigation Bar
        tk.Frame(right, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew")
        footer = tk.Frame(right, bg=BG_CARD, padx=26, pady=12)
        footer.grid(row=2, column=0, sticky="ew")
        self.back_btn = self._btn(footer, "← Quay lại", self._prev_page, kind="secondary")
        self.back_btn.pack(side="left")
        self.rollback_btn = self._btn(footer, "↩️ Hoàn tác backup", self._rollback, kind="secondary")
        self.rollback_btn.pack(side="left", padx=10)

        self.start_btn = self._btn(footer, "🚀 Bắt đầu cài đặt ngay", self._start_install, kind="primary", pad_x=20, pad_y=8)
        self.start_btn.pack(side="right")
        self.next_btn = self._btn(footer, "Tiếp tục →", self._next_page, kind="info", pad_x=16, pad_y=8)
        self.next_btn.pack(side="right", padx=(0, 10))

    # ---- PAGE 1: Overview & Modular Selection ----
    def _build_page_overview(self):
        p = tk.Frame(self.page_host, bg=BG_CANVAS)
        self.pages["overview"] = p

        tk.Label(p, text="Tổng quan & Chọn phần cài đặt", font=("Segoe UI", 17, "bold"), bg=BG_CANVAS, fg=TEXT_MAIN).pack(anchor="w")
        tk.Label(p, text="Bộ cài tự động nối vào OpenClaw đang có trên máy. Tích chọn đúng các tính năng khách hàng cần dùng.",
                 font=("Segoe UI", 10), bg=BG_CANVAS, fg=TEXT_SUB).pack(anchor="w", pady=(3, 16))

        # OpenClaw Detection Card
        c1_out, c1 = self._card(p, pad=16)
        c1_out.pack(fill="x", pady=(0, 16))
        tk.Label(c1, text="Hệ thống OpenClaw phát hiện trên máy", font=("Segoe UI", 11, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w")
        self.det_badge = tk.Label(c1, text="Đang kiểm tra...", font=("Segoe UI", 10, "bold"), bg=BG_INFO, fg=PRIMARY, padx=10, pady=6, anchor="w")
        self.det_badge.pack(fill="x", pady=(10, 6))
        self.det_meta = tk.Label(c1, text="", font=("Segoe UI", 9), bg=BG_CARD, fg=TEXT_SUB, anchor="w", justify="left")
        self.det_meta.pack(fill="x")

        # 4 Modular Cards
        c2_out, c2 = self._card(p, pad=16)
        c2_out.pack(fill="both", expand=True)
        tk.Label(c2, text="Chọn các module muốn cài đặt (Cài từng phần)", font=("Segoe UI", 11, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w", pady=(0, 10))

        modules = [
            ("video", self.mod_video_var, "🎬 Tạo Video tự động (9:16 · 16:9 · 1:1)", "Giọng đọc tiếng Việt (edge-tts + gTTS dự phòng), ảnh AI, Pixabay miễn phí, phụ đề HyperFrames."),
            ("google", self.mod_google_var, "📊 Sổ duyệt Google Sheet & Drive (Tuỳ chọn)", "Tự ghi video vào Google Sheet (PA → PD → POSTED) để duyệt bài tự động từ xa."),
            ("facebook", self.mod_fb_var, "📘 Tự động đăng Facebook Fanpage (Tuỳ chọn)", "Đăng video trực tiếp lên Fanpage của khách qua Facebook Login hoặc Page Access Token."),
            ("youtube", self.mod_yt_var, "▶️ Tự động đăng YouTube Shorts / Video (Tuỳ chọn)", "Tự động tải video lên kênh YouTube của khách thông qua YouTube Data API v3."),
        ]
        for key, var, title, desc in modules:
            box = tk.Frame(c2, bg=BG_SUBTLE, highlightbackground=BORDER, highlightthickness=1, padx=12, pady=10)
            box.pack(fill="x", pady=5)
            top_r = tk.Frame(box, bg=BG_SUBTLE)
            top_r.pack(fill="x")
            tk.Checkbutton(top_r, text=title, variable=var, bg=BG_SUBTLE, fg=TEXT_MAIN, activebackground=BG_SUBTLE,
                           font=("Segoe UI", 10, "bold"), command=self._refresh_modular_ui).pack(side="left")
            badge = tk.Label(top_r, text="Chưa cài", font=("Segoe UI", 8, "bold"), bg="#E2E8F0", fg=TEXT_SUB, padx=8, pady=2)
            badge.pack(side="right")
            self.mod_badges[key] = badge
            tk.Label(box, text=desc, font=("Segoe UI", 9), bg=BG_SUBTLE, fg=TEXT_SUB, anchor="w").pack(anchor="w", padx=(24, 0), pady=(2, 0))

    # ---- PAGE 2: Bot Connection & Personal API Keys ----
    def _build_page_video(self):
        p = tk.Frame(self.page_host, bg=BG_CANVAS)
        self.pages["video"] = p

        tk.Label(p, text="Kết nối Bot OpenClaw & API Key cá nhân", font=("Segoe UI", 17, "bold"), bg=BG_CANVAS, fg=TEXT_MAIN).pack(anchor="w")
        tk.Label(p, text="Mặc định gắn trực tiếp chức năng tạo video vào Bot OpenClaw có sẵn của khách (không ảnh hưởng bot cũ).",
                 font=("Segoe UI", 10), bg=BG_CANVAS, fg=TEXT_SUB).pack(anchor="w", pady=(3, 16))

        c_out, c = self._card(p, pad=20)
        c_out.pack(fill="x")
        c.columnconfigure(0, weight=0, minsize=185)
        c.columnconfigure(1, weight=1, minsize=280)
        c.columnconfigure(2, weight=0)

        # Mode Selector
        m_row = tk.Frame(c, bg=BG_INFO, padx=14, pady=10)
        m_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        tk.Label(m_row, text="Chế độ cài:", font=("Segoe UI", 10, "bold"), bg=BG_INFO, fg=TEXT_MAIN).pack(side="left")
        tk.Radiobutton(m_row, text="Gắn vào Bot hiện có (Khuyên dùng)", variable=self.mode_var, value="existing_bot",
                       bg=BG_INFO, fg=TEXT_MAIN, activebackground=BG_INFO, font=("Segoe UI", 10), command=self._toggle_mode).pack(side="left", padx=(14, 18))
        tk.Radiobutton(m_row, text="Tạo thêm Bot Video riêng", variable=self.mode_var, value="separate_bot",
                       bg=BG_INFO, fg=TEXT_MAIN, activebackground=BG_INFO, font=("Segoe UI", 10), command=self._toggle_mode).pack(side="left")

        # Bot Token row (hidden unless separate_bot)
        self.tok_lbl = tk.Label(c, text="Telegram Bot Token:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 10, "bold"))
        self.tok_wrap, self.token_entry = self._entry(c, self.token_var)
        self.check_tok_btn = self._btn(c, "Kiểm tra Bot", self._check_token, kind="secondary", pad_x=10, pad_y=5)

        # Owner ID
        tk.Label(c, text="Telegram ID chủ máy:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=8)
        own_wrap, _ = self._entry(c, self.owner_var)
        own_wrap.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=8)

        # Personal API Key
        tk.Label(c, text="API Key cá nhân:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(8, 2))
        api_wrap, self.api_entry = self._entry(c, self.api_var, show="*")
        api_wrap.grid(row=3, column=1, sticky="ew", padx=10, pady=(8, 2))
        api_btns = tk.Frame(c, bg=BG_CARD)
        api_btns.grid(row=3, column=2, pady=(8, 2))
        self.toggle_api_btn = self._btn(api_btns, "Hiện", self._toggle_api_vis, kind="secondary", pad_x=8, pad_y=5)
        self.toggle_api_btn.pack(side="left", padx=(0, 6))
        self._btn(api_btns, "Kiểm tra Key", self._check_api, kind="info", pad_x=10, pad_y=5).pack(side="left")

        hint_r = tk.Frame(c, bg=BG_CARD)
        hint_r.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(0, 8))
        tk.Label(hint_r, text="Dùng tạo ảnh AI & gọi Codex tự sửa lỗi.", font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_SUB).pack(side="left")
        self.use_existing_api_btn = tk.Button(hint_r, text="Lấy key sẵn từ OpenClaw", command=self._load_existing_api,
                                              bg=BG_INFO, fg=PRIMARY, relief="flat", font=("Segoe UI", 8, "bold"), padx=8, pady=2, cursor="hand2")

        # Pixabay API Key
        tk.Label(c, text="Pixabay API Key (tuỳ chọn):", bg=BG_CARD, fg=TEXT_SUB, font=("Segoe UI", 10)).grid(row=5, column=0, sticky="w", pady=(8, 2))
        px_wrap, _ = self._entry(c, self.pixabay_var)
        px_wrap.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(8, 2))
        tk.Label(c, text="Kho video/ảnh nền miễn phí 100% — lấy nhanh tại pixabay.com/api/docs", font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_SUB).grid(
            row=6, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(0, 10)
        )

        # Optional Brand Logo Row (tích hoặc không tích)
        logo_chk_row = tk.Frame(c, bg=BG_CARD)
        logo_chk_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        tk.Checkbutton(
            logo_chk_row, text="Gắn logo thương hiệu lên mọi video (tuỳ chọn)",
            variable=self.logo_en_var, bg=BG_CARD, fg=TEXT_MAIN, activebackground=BG_CARD,
            font=("Segoe UI", 9, "bold"), command=self._toggle_logo_row,
        ).pack(side="left")

        self.logo_lbl = tk.Label(c, text="File logo (.png/.jpg):", bg=BG_CARD, fg=TEXT_SUB, font=("Segoe UI", 9))
        self.logo_wrap, _ = self._entry(c, self.logo_path_var)
        self.logo_pick_btn = self._btn(c, "Chọn logo...", self._pick_brand_logo, kind="secondary", pad_x=10, pad_y=4)

        # Codex Self-Heal card
        heal_box = tk.Frame(c, bg=BG_WARN, padx=12, pady=10)
        heal_box.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        tk.Checkbutton(
            heal_box,
            text="Bật Codex AI Tự Sửa Lỗi (tự dùng Codex CLI hoặc API Key ở trên để tự sửa nếu gặp lỗi cài đặt)",
            variable=self.heal_var, bg=BG_WARN, fg="#92400E", activebackground=BG_WARN, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        self._toggle_mode()
        self._toggle_logo_row()

    # ---- PAGE 3: Auto-Publish (Google / Facebook / YouTube) ----
    def _build_page_social(self):
        p = tk.Frame(self.page_host, bg=BG_CANVAS)
        self.pages["social"] = p

        tk.Label(p, text="Cấu hình Tự động đăng bài (Tuỳ chọn)", font=("Segoe UI", 17, "bold"), bg=BG_CANVAS, fg=TEXT_MAIN).pack(anchor="w")
        tk.Label(p, text="Chỉ hiển thị các kênh bạn đã tích chọn ở Bước 1. Hỗ trợ đăng nhập 1-click hoặc nhập thủ công.",
                 font=("Segoe UI", 10), bg=BG_CANVAS, fg=TEXT_SUB).pack(anchor="w", pady=(3, 14))

        self.soc_empty_card, soc_e = self._card(p, pad=24)
        tk.Label(soc_e, text="Bạn chưa chọn kênh đăng bài nào (Google Sheet / Facebook / YouTube).",
                 font=("Segoe UI", 11, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w")
        tk.Label(soc_e, text="Nếu chỉ cần tính năng Tạo Video 9:16 / 16:9 / 1:1, bạn có thể bấm 'Tiếp tục' hoặc 'Bắt đầu cài đặt ngay'.\nNếu muốn bật thêm kênh đăng bài, quay lại Bước 1 để tích chọn.",
                 font=("Segoe UI", 10), bg=BG_CARD, fg=TEXT_SUB, justify="left").pack(anchor="w", pady=(8, 0))

        # Google Card
        self.google_card, gc = self._card(p, pad=14)
        gc.columnconfigure(1, weight=1)
        g_hdr = tk.Frame(gc, bg=BG_CARD)
        g_hdr.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        tk.Label(g_hdr, text="📊 Google Sheet & Drive (Sổ duyệt PA → PD → POSTED)", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=PRIMARY).pack(side="left")
        self._btn(g_hdr, "🔐 Đăng nhập Google & Tạo Sheet", self._oauth_google, kind="info", pad_x=10, pad_y=4).pack(side="right")
        tk.Label(gc, text="Link Google Sheet:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=3)
        w, _ = self._entry(gc, self.gs_url_var)
        w.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3)
        tk.Label(gc, text="File Google Key (.json):", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=3)
        w, _ = self._entry(gc, self.gs_cred_var)
        w.grid(row=2, column=1, sticky="ew", padx=8, pady=3)
        self._btn(gc, "Chọn file...", self._pick_google_json, kind="secondary", pad_x=10, pad_y=4).grid(row=2, column=2, pady=3)
        tk.Label(gc, text="Link Google Drive:", bg=BG_CARD, fg=TEXT_SUB, font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=3)
        w, _ = self._entry(gc, self.gd_url_var)
        w.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3)

        # Facebook Card
        self.fb_card, fc = self._card(p, pad=14)
        fc.columnconfigure(1, weight=1)
        f_hdr = tk.Frame(fc, bg=BG_CARD)
        f_hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        tk.Label(f_hdr, text="📘 Facebook Fanpage", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=PRIMARY).pack(side="left")
        self._btn(f_hdr, "🔐 Đăng nhập Facebook & Chọn Fanpage", self._oauth_facebook, kind="info", pad_x=10, pad_y=4).pack(side="right")
        self.fb_picker = ttk.Combobox(f_hdr, textvariable=self.fb_picker_var, state="readonly", width=26)
        self.fb_picker.bind("<<ComboboxSelected>>", self._on_pick_fanpage)
        tk.Label(fc, text="Facebook Page ID:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=3)
        w, _ = self._entry(fc, self.fb_id_var)
        w.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        tk.Label(fc, text="Page Access Token:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=3)
        w, _ = self._entry(fc, self.fb_tok_var, show="*")
        w.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)

        # YouTube Card
        self.yt_card, yc = self._card(p, pad=14)
        yc.columnconfigure(1, weight=1)
        tk.Label(yc, text="▶️ YouTube Shorts / Video", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=PRIMARY).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(yc, text="Link kênh YouTube:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=3)
        w, _ = self._entry(yc, self.yt_url_var)
        w.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        tk.Label(yc, text="Client ID / Secret:", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=3)
        yt_box = tk.Frame(yc, bg=BG_CARD)
        yt_box.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
        yt_box.columnconfigure(0, weight=1)
        yt_box.columnconfigure(1, weight=1)
        w1, _ = self._entry(yt_box, self.yt_cid_var, width=18)
        w2, _ = self._entry(yt_box, self.yt_csec_var, show="*", width=18)
        w1.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        w2.grid(row=0, column=1, sticky="ew")

        self._refresh_modular_ui()

    # ---- PAGE 4: Dedicated 7-Step Progress & Live Log ----
    def _build_page_install(self):
        p = tk.Frame(self.page_host, bg=BG_CANVAS)
        self.pages["install"] = p
        p.rowconfigure(2, weight=1)
        p.columnconfigure(0, weight=1)

        hdr = tk.Frame(p, bg=BG_CANVAS)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        tk.Label(hdr, text="Tiến độ cài đặt & Nhật ký trực tiếp", font=("Segoe UI", 17, "bold"), bg=BG_CANVAS, fg=TEXT_MAIN).pack(side="left")
        self._btn(hdr, "🛠️ Gọi Codex tự sửa lỗi", self._manual_heal, kind="warn", pad_x=12, pad_y=6).pack(side="right")

        # 7-Step Card
        st_out, st = self._card(p, pad=16)
        st_out.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        top_s = tk.Frame(st, bg=BG_CARD)
        top_s.pack(fill="x", pady=(0, 6))
        tk.Label(top_s, text="Tiến độ 7 bước cài đặt", font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(side="left")
        self.pct_lbl = tk.Label(top_s, text="0 / 7 bước hoàn tất", font=("Segoe UI", 9, "bold"), bg=BG_CARD, fg=PRIMARY)
        self.pct_lbl.pack(side="right")
        self.pbar = ttk.Progressbar(st, mode="determinate", maximum=len(STEPS))
        self.pbar.pack(fill="x", pady=(0, 10))

        for i, title in enumerate(STEPS):
            row = tk.Frame(st, bg=BG_SUBTLE, padx=10, pady=6)
            row.pack(fill="x", pady=2)
            dot = tk.Label(row, text="●", font=("Segoe UI", 10, "bold"), bg=BG_SUBTLE, fg="#CBD5E1", width=2)
            dot.pack(side="left")
            t_lbl = tk.Label(row, text=f"Bước {i + 1}: {title}", font=("Segoe UI", 9, "bold"), bg=BG_SUBTLE, fg=TEXT_MAIN)
            t_lbl.pack(side="left")
            d_lbl = tk.Label(row, text="Chờ thực hiện", font=("Segoe UI", 9), bg=BG_SUBTLE, fg=TEXT_SUB)
            d_lbl.pack(side="right")
            self.step_widgets.append((row, dot, t_lbl, d_lbl))

        # Live Log Card
        log_out, log_in = self._card(p, pad=12)
        log_out.grid(row=2, column=0, sticky="nsew")
        tk.Label(log_in, text="Nhật ký chi tiết (Live Log)", font=("Segoe UI", 9, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(anchor="w", pady=(0, 6))
        self.log_box = scrolledtext.ScrolledText(log_in, bg="#0F172A", fg="#E2E8F0", font=("Consolas", 9), relief="flat", height=10)
        self.log_box.pack(fill="both", expand=True)

    # ---- Navigation & State Helpers ----
    def _show_page(self, key: str):
        self.current_page = key
        for k, frame in self.pages.items():
            if k == key:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.config(bg=BG_INFO, fg=PRIMARY, font=("Segoe UI", 10, "bold"))
            else:
                btn.config(bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 10))
        order = ["overview", "video", "social", "install"]
        idx = order.index(key)
        self.back_btn.config(state="normal" if idx > 0 else "disabled")
        self.next_btn.config(state="normal" if idx < len(order) - 1 else "disabled")

    def _next_page(self):
        order = ["overview", "video", "social", "install"]
        idx = order.index(self.current_page)
        if idx < len(order) - 1:
            self._show_page(order[idx + 1])

    def _prev_page(self):
        order = ["overview", "video", "social", "install"]
        idx = order.index(self.current_page)
        if idx > 0:
            self._show_page(order[idx - 1])

    def _populate_detected(self):
        if self.env.found:
            self.det_badge.config(text="✅ Đã phát hiện OpenClaw đang cài đặt trên máy", bg=BG_SUCCESS, fg=SUCCESS)
            cx = "Có sẵn Codex CLI" if self.env.codex_cmd else "Dùng Codex API dự phòng"
            self.det_meta.config(text=f"Thư mục: {self.env.state_dir}   |   Agents: {', '.join(self.env.existing_agents) or 'main'}   |   {cx}")
            self.sb_status_lbl.config(text="● OpenClaw: Sẵn sàng", fg=SUCCESS)
            if self.env.existing_owners:
                self.owner_var.set(", ".join(self.env.existing_owners))
            if self.env.existing_api_key:
                self.use_existing_api_btn.pack(side="right")
                self._append_log("Phát hiện OpenClaw có sẵn API key — khách có thể nhập key riêng hoặc bấm 'Lấy key sẵn từ OpenClaw'.")
            self._refresh_installed_badges(prefill=True)
        else:
            self.det_badge.config(text="⚠️ Chưa phát hiện OpenClaw trên máy này", bg=BG_DANGER, fg=DANGER)
            self.det_meta.config(text="Vui lòng cài đặt OpenClaw trước khi chạy bộ cài tạo video này.")
            self.sb_status_lbl.config(text="● OpenClaw: Chưa cài", fg=DANGER)

    def _refresh_installed_badges(self, prefill: bool = False):
        if not self.env.found:
            return
        st = detect_installed_modules(self.env.state_dir)
        for key, badge in self.mod_badges.items():
            if st.get(key):
                badge.config(text="✓ Đã cài", bg=BG_SUCCESS, fg=SUCCESS)
            else:
                badge.config(text="Chưa cài", bg="#E2E8F0", fg=TEXT_SUB)
        if prefill:
            cfg = st.get("social_cfg") or {}
            gs, gd, fb, yt = cfg.get("google_sheet") or {}, cfg.get("google_drive") or {}, cfg.get("facebook") or {}, cfg.get("youtube") or {}
            if gs.get("url") and not self.gs_url_var.get():
                self.gs_url_var.set(gs["url"])
            if gd.get("folder_url") and not self.gd_url_var.get():
                self.gd_url_var.set(gd["folder_url"])
            if fb.get("page_id") and not self.fb_id_var.get():
                self.fb_id_var.set(fb["page_id"])
            if yt.get("channel_url") and not self.yt_url_var.get():
                self.yt_url_var.set(yt["channel_url"])

    def _refresh_modular_ui(self):
        for w in (self.soc_empty_card, self.google_card, self.fb_card, self.yt_card):
            w.pack_forget()
        any_soc = False
        if self.mod_google_var.get():
            self.google_card.pack(fill="x", pady=(0, 10))
            any_soc = True
        if self.mod_fb_var.get():
            self.fb_card.pack(fill="x", pady=(0, 10))
            any_soc = True
        if self.mod_yt_var.get():
            self.yt_card.pack(fill="x", pady=(0, 10))
            any_soc = True
        if not any_soc:
            self.soc_empty_card.pack(fill="x", pady=6)

    def _toggle_mode(self):
        is_sep = self.mode_var.get() == "separate_bot"
        if is_sep:
            self.tok_lbl.grid(row=1, column=0, sticky="w", pady=(6, 4))
            self.tok_wrap.grid(row=1, column=1, sticky="ew", padx=10, pady=(6, 4))
            self.check_tok_btn.grid(row=1, column=2, pady=(6, 4))
            self.token_entry.config(state="normal")
            self.token_entry.focus_set()
        else:
            self.tok_lbl.grid_remove()
            self.tok_wrap.grid_remove()
            self.check_tok_btn.grid_remove()

    def _load_existing_api(self):
        if self.env.existing_api_key:
            self.api_var.set(self.env.existing_api_key)
            self._append_log("Đã điền API Key từ cấu hình OpenClaw hiện tại.")

    def _toggle_api_vis(self):
        self.show_api = not self.show_api
        self.api_entry.config(show="" if self.show_api else "*")
        self.toggle_api_btn.config(text="Ẩn" if self.show_api else "Hiện")

    def _toggle_logo_row(self):
        if self.logo_en_var.get():
            self.logo_lbl.grid(row=8, column=0, sticky="w", pady=4)
            self.logo_wrap.grid(row=8, column=1, sticky="ew", padx=10, pady=4)
            self.logo_pick_btn.grid(row=8, column=2, pady=4)
        else:
            self.logo_lbl.grid_remove()
            self.logo_wrap.grid_remove()
            self.logo_pick_btn.grid_remove()

    def _pick_brand_logo(self):
        p = filedialog.askopenfilename(title="Chọn file logo thương hiệu", filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp"), ("All files", "*.*")])
        if p:
            self.logo_path_var.set(p)

    def _pick_google_json(self):
        p = filedialog.askopenfilename(title="Chọn file Google Service Account JSON", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p:
            self.gs_cred_var.set(p)

    def _oauth_google(self):
        if not self.env.found:
            messagebox.showwarning("Chưa thấy OpenClaw", "Không tìm thấy thư mục OpenClaw để lưu token.")
            return
        bundled = load_bundled_oauth_config().get("google") or {}
        cid = self.yt_cid_var.get().strip() or (bundled.get("client_id") or "").strip()
        csec = self.yt_csec_var.get().strip() or (bundled.get("client_secret") or "").strip()
        secrets_dir = Path(self.env.state_dir) / "video-factory" / "secrets"
        self._append_log("Đang mở trình duyệt đăng nhập Google (OAuth 1-click)...")
        def worker():
            res = connect_google_and_create_sheet(cid, csec, secrets_dir)
            if res.get("ok"):
                if res.get("sheet_url"):
                    self.after(0, lambda: self.gs_url_var.set(res["sheet_url"]))
                msg = f"✅ Đã kết nối Google thành công!\nSổ duyệt Sheet: {res.get('sheet_url') or '(đã lưu token)'}"
                self._append_log(msg)
                self.after(0, lambda: messagebox.showinfo("Kết nối Google thành công", msg))
            else:
                self._append_log(f"❌ Lỗi kết nối Google: {res.get('error')}")
                self.after(0, lambda: messagebox.showerror("Lỗi Google OAuth", str(res.get("error"))))
        threading.Thread(target=worker, daemon=True).start()

    def _oauth_facebook(self):
        bundled = load_bundled_oauth_config().get("facebook") or {}
        app_id = (bundled.get("app_id") or "").strip()
        app_sec = (bundled.get("app_secret") or "").strip()
        self._append_log("Đang mở trình duyệt đăng nhập Facebook để lấy danh sách Fanpage...")
        def worker():
            res = connect_facebook_get_pages(app_id, app_sec)
            if res.get("ok"):
                self.fb_pages = res["pages"]
                names = [f"{p['name']} ({p['id']})" for p in self.fb_pages]
                def update_picker():
                    self.fb_picker["values"] = names
                    self.fb_picker.pack(side="right", padx=(0, 8))
                    self.fb_picker.current(0)
                    self._on_pick_fanpage(None)
                self.after(0, update_picker)
                self._append_log(f"✅ Đã lấy {len(self.fb_pages)} Fanpage từ Facebook.")
            else:
                self._append_log(f"❌ Lỗi kết nối Facebook: {res.get('error')}")
                self.after(0, lambda: messagebox.showerror("Lỗi Facebook Login", str(res.get("error"))))
        threading.Thread(target=worker, daemon=True).start()

    def _on_pick_fanpage(self, _evt):
        idx = self.fb_picker.current()
        if 0 <= idx < len(self.fb_pages):
            page = self.fb_pages[idx]
            self.fb_id_var.set(page["id"])
            self.fb_tok_var.set(page["access_token"])
            self._append_log(f"Đã chọn Fanpage: {page['name']} (ID: {page['id']})")

    def _append_log(self, msg: str):
        self.after(0, lambda: (self.log_box.insert("end", msg + "\n"), self.log_box.see("end")))

    def _set_step(self, idx: int, state: str, detail: str):
        def _do():
            icon, dot_fg, text_fg, default_txt = STEP_BADGES.get(state, STEP_BADGES["pending"])
            row, dot, t_lbl, d_lbl = self.step_widgets[idx]
            bg = BG_SUCCESS if state == "done" else (BG_INFO if state == "running" else (BG_WARN if state == "healing" else (BG_DANGER if state == "error" else BG_SUBTLE)))
            for w in (row, dot, t_lbl, d_lbl):
                w.config(bg=bg)
            dot.config(text=icon, fg=dot_fg)
            d_lbl.config(text=detail or default_txt, fg=text_fg)
            done_count = sum(1 for _, d, _, _ in self.step_widgets if d.cget("text") in ("✓", "⏭"))
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
                msg = f"❌ API Key không hợp lệ: {res.get('error')}"
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
            messagebox.showwarning("Chưa chọn module", "Vui lòng tích chọn ít nhất 1 phần muốn cài ở Bước 1.")
            self._show_page("overview")
            return
        mode = self.mode_var.get()
        if self.mod_video_var.get() and mode == "separate_bot" and not self.token_var.get().strip():
            messagebox.showwarning("Thiếu Bot Token", "Vui lòng nhập Telegram Bot Token (hoặc chọn 'Gắn vào Bot hiện có').")
            self._show_page("video")
            return
        if self.mod_video_var.get() and not self.api_var.get().strip():
            messagebox.showwarning("Thiếu API Key", "Vui lòng nhập API Key cá nhân (hoặc bấm 'Lấy key sẵn từ OpenClaw').")
            self._show_page("video")
            return

        # Automatically switch to dedicated Progress & Live Log page
        self._show_page("install")
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
            pixabay_key=self.pixabay_var.get().strip(),
            enable_codex_heal=self.heal_var.get(),
            brand_logo_enabled=self.logo_en_var.get(),
            brand_logo_path=self.logo_path_var.get().strip(),
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
                    messagebox.showinfo("Hoàn tất!", "Đã cài xong OpenClaw Video Factory!\n\nMở Telegram nhắn cho bot để tạo video 9:16, 16:9 hoặc 1:1 ngay.")
                else:
                    messagebox.showerror("Có lỗi xảy ra", "Cài đặt gặp lỗi. Xem Nhật ký hoặc bấm 'Gọi Codex tự sửa lỗi'.")
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
                [self.token_var.get().strip(), self.api_var.get().strip(), self.pixabay_var.get().strip()],
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
