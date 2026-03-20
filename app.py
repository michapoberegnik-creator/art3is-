from __future__ import annotations

import random
import re
import subprocess
import sys
import tkinter as tk
import webbrowser
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote_plus

try:
    import vlc  # type: ignore
except Exception:
    vlc = None

from server_backend import (
    EmbeddedServer,
    EQ_PRESETS,
    SPEED_PRESETS,
    TOKEN_FIELDS,
    add_track_to_playlist,
    build_recommendation_foundation,
    build_search_results,
    create_playlist,
    get_ui,
    get_track_key,
    import_background_source,
    import_track_path,
    is_favorite,
    load_state,
    record_play_event,
    remove_track_from_playlist,
    resolve_background_path,
    save_state,
    save_custom_wave,
    set_current_track,
    toggle_favorite,
)


BG = "#05090d"
SURFACE = "#0a1118"
SURFACE_ALT = "#0e1822"
INPUT_BG = "#08121a"
LINE = "#163344"
TEXT = "#f2f8fc"
MUTED = "#89a3b5"
ACCENT = "#4be3ff"
ACCENT_STRONG = "#18b7dc"
ACCENT_SOFT = "#b7f6ff"
CHIP = "#102433"

getcontext().prec = 28

APP_DIR = Path(__file__).resolve().parent
JS_EQUALIZER_PAGE = APP_DIR / "web_equalizer.html"
EMBED_PORTAL_PAGE = APP_DIR / "embed_portal.html"
EMBED_PLAYER_HELPER = APP_DIR / "embed_player_window.py"


class PlaybackEngine:
    def __init__(self) -> None:
        self.available = vlc is not None
        self.instance = vlc.Instance() if self.available else None
        self.player = self.instance.media_player_new() if self.available else None

    def load(self, path: str) -> None:
        if self.available and self.player:
            self.player.set_media(self.instance.media_new(path))

    def play(self) -> None:
        if self.available and self.player:
            self.player.play()

    def pause(self) -> None:
        if self.available and self.player:
            self.player.pause()

    def stop(self) -> None:
        if self.available and self.player:
            self.player.stop()

    def apply(self, eq_name: str, speed_name: str, custom_eq: dict[str, int] | None = None) -> None:
        if self.available and self.player:
            profile = custom_eq if eq_name == "Custom" and custom_eq else EQ_PRESETS.get(eq_name, EQ_PRESETS["Flat"])
            equalizer = vlc.libvlc_audio_equalizer_new()
            band_values = [
                profile.get("low", 0),
                profile.get("low", 0),
                profile.get("low", 0),
                profile.get("mid", 0),
                profile.get("mid", 0),
                profile.get("mid", 0),
                profile.get("mid", 0),
                profile.get("high", 0),
                profile.get("high", 0),
                profile.get("high", 0),
            ]
            for band_index, value in enumerate(band_values):
                vlc.libvlc_audio_equalizer_set_amp_at_index(equalizer, float(value), band_index)
            self.player.set_equalizer(equalizer)
            self.player.set_rate(SPEED_PRESETS.get(speed_name, 1.0))

    def get_time_ms(self) -> int | None:
        if not self.available or not self.player:
            return None
        current = self.player.get_time()
        return current if current >= 0 else None


class MusicDeskApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("PulseDock Studio")
        self.root.geometry("1300x860")
        self.root.minsize(1180, 760)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.engine = PlaybackEngine()
        self.state = load_state()
        self.ui = get_ui(self.state)
        self.search_results: list[dict] = []

        try:
            self.server = EmbeddedServer()
            self.server.start()
            self.server_status = f"{self.ui['status_ready']}: {self.server.base_url}"
        except OSError as exc:
            self.server = None
            self.server_status = f"Server unavailable: {exc}"

        current_track = self.state.get("current_track") or {}
        self.search_var = tk.StringVar(value=current_track.get("title", ""))
        self.track_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.language_var = tk.StringVar(value=self.state.get("language", "en"))
        self.eq_var = tk.StringVar(value=self.state.get("eq_preset", "Classic"))
        self.speed_var = tk.StringVar(value=self.state.get("speed_preset", "Normal"))
        self.bg_var = tk.StringVar()
        self.calc_var = tk.StringVar(value="0")
        self.calc_history_var = tk.StringVar(value="")
        custom_eq = self.state.get("custom_eq", {})
        self.eq_low_var = tk.IntVar(value=int(custom_eq.get("low", 0)))
        self.eq_mid_var = tk.IntVar(value=int(custom_eq.get("mid", 0)))
        self.eq_high_var = tk.IntVar(value=int(custom_eq.get("high", 0)))
        self.token_vars = {field: tk.StringVar(value=self.state.get("tokens", {}).get(field, "")) for field, _ in TOKEN_FIELDS}

        self.bg_label: tk.Label | None = None
        self.bg_frames: list[tk.PhotoImage] = []
        self.bg_job: str | None = None
        self.bg_static: tk.PhotoImage | None = None
        self.timecode_var = tk.StringVar(value="00:00.00")
        self.lyrics_status_var = tk.StringVar(value="No synced text loaded.")
        self.lyrics_lines: list[tuple[int, str]] = []
        self.active_lyric_index: int | None = None
        self.lyrics_job: str | None = None
        self.lyrics_editor: tk.Text | None = None
        self.lyrics_list: tk.Listbox | None = None
        self.recommendation_list: tk.Listbox | None = None
        self.recommendation_browser_list: tk.Listbox | None = None
        self.recommendation_reason_var = tk.StringVar(value="No recommendation selected.")
        self.wave_name_var = tk.StringVar()
        self.wave_keywords_var = tk.StringVar()
        self.wave_choice_var = tk.StringVar()
        self.recommendation_items: list[dict] = []
        self.playlist_name_var = tk.StringVar()
        self.playlist_choice_var = tk.StringVar()
        self.library_browser_tree: ttk.Treeview | None = None
        self.favorite_tracks_list: tk.Listbox | None = None
        self.playlist_list: tk.Listbox | None = None
        self.playlist_tracks_list: tk.Listbox | None = None
        self.playlist_tracks_keys: list[str] = []

        self.spots_score = 0
        self.spots_best = 0
        self.spots_job: str | None = None
        self.spots_end_job: str | None = None

        self.snake_score = 0
        self.snake_best = 0
        self.snake_job: str | None = None
        self.snake_dir = (1, 0)
        self.snake_next = (1, 0)
        self.snake = [(4, 8), (3, 8), (2, 8)]
        self.food = (10, 10)

        self.calc_accumulator: Decimal | None = None
        self.calc_pending_op: str | None = None
        self.calc_last_operand: Decimal | None = None
        self.calc_new_entry = True
        self.calc_display: tk.Entry | None = None
        self.section_buttons: dict[str, ttk.Button] = {}
        self.section_frames: dict[str, ttk.Frame] = {}
        self.content_title_var = tk.StringVar(value="Tracks")
        self.content_subtitle_var = tk.StringVar(value="Local playback, web embeds, and synced text.")

        self.configure_styles()
        self.build_ui()
        self.refresh_all()
        self.schedule_lyrics_sync()
        self.root.bind("<Up>", lambda _e: self.queue_dir((0, -1)))
        self.root.bind("<Down>", lambda _e: self.queue_dir((0, 1)))
        self.root.bind("<Left>", lambda _e: self.queue_dir((-1, 0)))
        self.root.bind("<Right>", lambda _e: self.queue_dir((1, 0)))

    def configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=INPUT_BG)
        style.configure("TFrame", background=BG)
        style.configure("Sidebar.TFrame", background=SURFACE, relief="flat")
        style.configure("Hero.TFrame", background=SURFACE, relief="flat")
        style.configure("Card.TFrame", background=SURFACE, relief="flat")
        style.configure("Inset.TFrame", background=SURFACE_ALT, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Bahnschrift", 10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Bahnschrift", 22, "bold"))
        style.configure("HeroSub.TLabel", background=BG, foreground=MUTED, font=("Bahnschrift", 11))
        style.configure("Head.TLabel", background=SURFACE, foreground=TEXT, font=("Bahnschrift", 12, "bold"))
        style.configure("Micro.TLabel", background=SURFACE, foreground=MUTED, font=("Bahnschrift", 9))
        style.configure("HeroTitle.TLabel", background=SURFACE, foreground=TEXT, font=("Bahnschrift", 28, "bold"))
        style.configure("HeroLead.TLabel", background=SURFACE, foreground=ACCENT_SOFT, font=("Bahnschrift", 12))
        style.configure("HeroMeta.TLabel", background=SURFACE, foreground=MUTED, font=("Bahnschrift", 11))
        style.configure("CardBody.TLabel", background=SURFACE, foreground=MUTED, font=("Bahnschrift", 10))
        style.configure("InsetBody.TLabel", background=SURFACE_ALT, foreground=MUTED, font=("Bahnschrift", 10))
        style.configure("Chip.TLabel", background=CHIP, foreground=ACCENT_SOFT, font=("Bahnschrift", 9, "bold"))
        style.configure("StatLabel.TLabel", background=SURFACE_ALT, foreground=MUTED, font=("Bahnschrift", 9))
        style.configure("StatValue.TLabel", background=SURFACE_ALT, foreground=TEXT, font=("Bahnschrift", 18, "bold"))
        style.configure("SidebarTitle.TLabel", background=SURFACE, foreground=TEXT, font=("Bahnschrift", 15, "bold"))
        style.configure("SidebarMeta.TLabel", background=SURFACE, foreground=MUTED, font=("Bahnschrift", 10))
        style.configure("SidebarChip.TLabel", background=CHIP, foreground=ACCENT_SOFT, font=("Bahnschrift", 9, "bold"))
        style.configure("Nav.TButton", padding=(16, 12), background=SURFACE, foreground=MUTED, borderwidth=0, anchor="w")
        style.map("Nav.TButton", background=[("active", "#102331")], foreground=[("active", TEXT)])
        style.configure("NavActive.TButton", padding=(16, 12), background=ACCENT_STRONG, foreground=TEXT, borderwidth=0, anchor="w")
        style.map("NavActive.TButton", background=[("active", ACCENT)], foreground=[("active", TEXT)])
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 8))
        style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(22, 12), borderwidth=0)
        style.map(
            "TNotebook.Tab",
            background=[("selected", SURFACE_ALT), ("active", "#122231")],
            foreground=[("selected", TEXT), ("active", TEXT)],
        )
        style.configure(
            "Treeview",
            background=INPUT_BG,
            fieldbackground=INPUT_BG,
            foreground=TEXT,
            rowheight=34,
            borderwidth=0,
        )
        style.configure("Treeview.Heading", background=SURFACE_ALT, foreground=MUTED, relief="flat")
        style.map("Treeview", background=[("selected", ACCENT_STRONG)], foreground=[("selected", TEXT)])
        style.configure("TButton", padding=(12, 8), background=SURFACE_ALT, foreground=TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#162432")], foreground=[("active", TEXT)])
        style.configure("Accent.TButton", background=ACCENT_STRONG, foreground=TEXT)
        style.map("Accent.TButton", background=[("active", ACCENT)], foreground=[("active", TEXT)])
        style.configure("Ghost.TButton", background=SURFACE, foreground=MUTED)
        style.map("Ghost.TButton", background=[("active", SURFACE_ALT)], foreground=[("active", TEXT)])
        style.configure("TEntry", padding=10, fieldbackground=INPUT_BG, foreground=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure("TCombobox", padding=8, fieldbackground=INPUT_BG, foreground=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowsize=14)

    def style_listbox(self, widget: tk.Listbox) -> None:
        widget.configure(
            bg=INPUT_BG,
            fg=TEXT,
            selectbackground=ACCENT_STRONG,
            selectforeground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=LINE,
            bd=0,
            activestyle="none",
            font=("Bahnschrift", 10),
        )

    def style_text(self, widget: tk.Text) -> None:
        widget.configure(
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=LINE,
            bd=0,
            font=("Bahnschrift", 10),
        )

    def style_canvas(self, widget: tk.Canvas) -> None:
        widget.configure(bg=INPUT_BG, highlightthickness=1, highlightbackground=LINE, bd=0, relief="flat")

    def show_section(self, section_key: str) -> None:
        section_meta = {
            "tracks": ("Tracks", "Local playback, search results, and synced text."),
            "library": ("Library", "Favourites, playlists, and imported track management."),
            "recommendations": ("Recommendations", "History-based discovery and your own saved waves."),
            "options": ("Options", "Playback settings, background customization, and service tokens."),
            "widgets": ("Widgets", "Compact mini tools in the same visual system."),
        }
        for key, frame in self.section_frames.items():
            if key == section_key:
                frame.tkraise()
        for key, button in self.section_buttons.items():
            button.configure(style="NavActive.TButton" if key == section_key else "Nav.TButton")
        title, subtitle = section_meta.get(section_key, ("Workspace", ""))
        self.content_title_var.set(title)
        self.content_subtitle_var.set(subtitle)

    def build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=18)
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text=self.ui["app_name"], style="SidebarTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(sidebar, text="Blue-black desktop player with cyan glass accents.", style="SidebarMeta.TLabel", wraplength=180).grid(row=1, column=0, sticky="w", pady=(6, 0))
        chips = ttk.Frame(sidebar, style="Sidebar.TFrame")
        chips.grid(row=2, column=0, sticky="w", pady=(16, 0))
        ttk.Label(chips, text="  LIVE SERVER  ", style="SidebarChip.TLabel").grid(row=0, column=0, padx=(0, 8))
        ttk.Label(chips, text="  LOCAL FIRST  ", style="SidebarChip.TLabel").grid(row=0, column=1)

        nav_specs = [
            ("tracks", "Tracks"),
            ("library", "Library"),
            ("recommendations", "Recommendations"),
            ("options", self.ui["options"]),
            ("widgets", "Widgets"),
        ]
        nav_box = ttk.Frame(sidebar, style="Sidebar.TFrame")
        nav_box.grid(row=3, column=0, sticky="ew", pady=(22, 0))
        for row_index, (key, label) in enumerate(nav_specs):
            button = ttk.Button(nav_box, text=label, style="Nav.TButton", command=lambda name=key: self.show_section(name))
            button.grid(row=row_index, column=0, sticky="ew", pady=(0, 8))
            self.section_buttons[key] = button

        sidebar_spacer = ttk.Frame(sidebar, style="Sidebar.TFrame")
        sidebar_spacer.grid(row=4, column=0, sticky="nsew")
        sidebar.rowconfigure(4, weight=1)
        ttk.Label(sidebar, text=self.server_status, style="SidebarMeta.TLabel", wraplength=180).grid(row=5, column=0, sticky="sw")

        content = ttk.Frame(shell)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        hero = ttk.Frame(content, style="Hero.TFrame", padding=22)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=1)
        left = ttk.Frame(hero, style="Hero.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.columnconfigure(0, weight=1)
        ttk.Label(left, textvariable=self.content_title_var, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(left, textvariable=self.content_subtitle_var, style="HeroLead.TLabel", wraplength=540).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(left, text=self.server_status, style="HeroMeta.TLabel", wraplength=540).grid(row=2, column=0, sticky="w", pady=(8, 0))

        stats = ttk.Frame(left, style="Hero.TFrame")
        stats.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        stat_values = (("Theme", "Blue Black"), ("Surface", "Glass"), ("Search", "Embedded"))
        for index, (label, value) in enumerate(stat_values):
            card = ttk.Frame(stats, style="Inset.TFrame", padding=12)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 10 if index < 2 else 0))
            stats.columnconfigure(index, weight=1)
            ttk.Label(card, text=label, style="StatLabel.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(card, text=value, style="StatValue.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        search_panel = ttk.Frame(hero, style="Inset.TFrame", padding=14)
        search_panel.grid(row=0, column=1, sticky="nsew")
        search_panel.columnconfigure(0, weight=1)
        ttk.Label(search_panel, text="Global Search", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(search_panel, text="Spotify, SoundCloud, YouTube Music, and transfer shortcuts in one place.", style="InsetBody.TLabel", wraplength=360).grid(row=1, column=0, sticky="w", pady=(6, 12))
        ttk.Entry(search_panel, textvariable=self.search_var, width=42).grid(row=2, column=0, sticky="ew")
        actions = ttk.Frame(search_panel, style="Inset.TFrame")
        actions.grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Button(actions, text=self.ui["search_platforms"], style="Accent.TButton", command=self.search_everywhere).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text=self.ui["open_all"], style="Ghost.TButton", command=self.open_all_results).grid(row=0, column=1)

        workspace = ttk.Frame(content)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)

        tracks_tab = ttk.Frame(workspace, padding=16)
        library_tab = ttk.Frame(workspace, padding=16)
        recommendations_tab = ttk.Frame(workspace, padding=16)
        options_tab = ttk.Frame(workspace, padding=16)
        widgets_tab = ttk.Frame(workspace, padding=16)
        for key, frame in (
            ("tracks", tracks_tab),
            ("library", library_tab),
            ("recommendations", recommendations_tab),
            ("options", options_tab),
            ("widgets", widgets_tab),
        ):
            frame.grid(row=0, column=0, sticky="nsew")
            self.section_frames[key] = frame

        self.build_tracks_tab(tracks_tab)
        self.build_library_tab(library_tab)
        self.build_recommendations_tab(recommendations_tab)
        self.build_options_tab(options_tab)
        self.build_arcade_tab(widgets_tab)
        self.show_section("tracks")

        footer = ttk.Frame(content, style="Card.TFrame", padding=12)
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel", wraplength=1200).pack(anchor="w")

    def build_tracks_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent, style="Card.TFrame", padding=16)
        top.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)
        ttk.Label(top, text=self.ui["current_track"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.track_var, style="CardBody.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 12))
        controls = ttk.Frame(top, style="Card.TFrame")
        controls.grid(row=2, column=0, sticky="w")
        ttk.Button(controls, text=self.ui["import_tracks"], style="Ghost.TButton", command=self.import_tracks).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(controls, text=self.ui["play"], style="Accent.TButton", command=self.play_current).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(controls, text=self.ui["pause"], style="Ghost.TButton", command=self.engine.pause).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(controls, text=self.ui["stop"], style="Ghost.TButton", command=self.engine.stop).grid(row=0, column=3)
        audio = ttk.Frame(top, style="Inset.TFrame", padding=12)
        audio.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Label(audio, text=self.ui["equalizer"]).grid(row=0, column=0, sticky="w")
        eq = ttk.Combobox(audio, textvariable=self.eq_var, values=list(EQ_PRESETS.keys()), state="readonly", width=18)
        eq.grid(row=0, column=1, padx=(8, 16))
        eq.bind("<<ComboboxSelected>>", lambda _e: self.save_audio())
        ttk.Label(audio, text=self.ui["speed"]).grid(row=0, column=2, sticky="w")
        speed = ttk.Combobox(audio, textvariable=self.speed_var, values=list(SPEED_PRESETS.keys()), state="readonly", width=18)
        speed.grid(row=0, column=3, padx=(8, 0))
        speed.bind("<<ComboboxSelected>>", lambda _e: self.save_audio())
        stage = ttk.Frame(top, style="Inset.TFrame", padding=10)
        stage.grid(row=0, column=1, rowspan=4, sticky="nsew", padx=(16, 0))
        stage.columnconfigure(0, weight=1)
        ttk.Label(stage, text="Playback Surface", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(stage, text="Built to mirror the reference mood: large title area, calm spacing, and cyan-lit controls.", style="InsetBody.TLabel", wraplength=320).grid(row=1, column=0, sticky="w", pady=(6, 10))
        spotlight = ttk.Frame(stage, style="Inset.TFrame", padding=14)
        spotlight.grid(row=2, column=0, sticky="nsew")
        spotlight.columnconfigure(0, weight=1)
        ttk.Label(spotlight, text="NOW PLAYING", style="Chip.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(spotlight, textvariable=self.track_var, style="Head.TLabel", wraplength=300).grid(row=1, column=0, sticky="w", pady=(14, 4))
        ttk.Label(spotlight, text="Native player for local files. Search services open in official embedded windows.", style="InsetBody.TLabel", wraplength=300).grid(row=2, column=0, sticky="w")
        bar = ttk.Frame(spotlight, style="Inset.TFrame", padding=10)
        bar.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        bar.columnconfigure(0, weight=3)
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Playback Lane", style="StatLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(bar, text=self.speed_var.get(), style="Chip.TLabel").grid(row=0, column=1, sticky="e")
        tk.Canvas(bar, width=220, height=6, bg=INPUT_BG, highlightthickness=0, bd=0).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        library = ttk.Frame(parent, style="Card.TFrame", padding=16)
        library.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        library.columnconfigure(0, weight=1)
        library.rowconfigure(1, weight=1)
        ttk.Label(library, text=self.ui["library"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.library_tree = ttk.Treeview(library, columns=("title", "source"), show="headings", selectmode="browse")
        self.library_tree.heading("title", text=self.ui["current_track"])
        self.library_tree.heading("source", text="Source")
        self.library_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.library_tree.bind("<<TreeviewSelect>>", self.on_library_select)

        right = ttk.Frame(parent)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        search = ttk.Frame(right, style="Card.TFrame", padding=16)
        search.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        search.columnconfigure(0, weight=1)
        search.rowconfigure(2, weight=1)
        ttk.Label(search, text=self.ui["search"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(search, text=self.ui["empty_results"], style="Muted.TLabel", wraplength=420).grid(row=1, column=0, sticky="w", pady=(4, 10))
        self.result_list = tk.Listbox(search)
        self.style_listbox(self.result_list)
        self.result_list.grid(row=2, column=0, sticky="nsew")
        self.result_list.bind("<Double-Button-1>", lambda _e: self.open_selected("url"))
        buttons = ttk.Frame(search)
        buttons.grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Button(buttons, text=self.ui["open_music"], style="Accent.TButton", command=lambda: self.open_selected("url")).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text=self.ui["open_text"], style="Ghost.TButton", command=lambda: self.open_selected("text_url")).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text=self.ui["open_all"], style="Ghost.TButton", command=self.open_all_results).grid(row=0, column=2)

        recommend = ttk.Frame(right, style="Card.TFrame", padding=16)
        recommend.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        recommend.columnconfigure(0, weight=1)
        ttk.Label(recommend, text="Recommendation Foundation", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(recommend, textvariable=self.recommendation_reason_var, style="Muted.TLabel", wraplength=420).grid(row=1, column=0, sticky="w", pady=(6, 10))
        self.recommendation_list = tk.Listbox(recommend, height=8)
        self.style_listbox(self.recommendation_list)
        self.recommendation_list.grid(row=2, column=0, sticky="nsew")
        self.recommendation_list.bind("<<ListboxSelect>>", self.on_recommendation_select)
        wave_row = ttk.Frame(recommend)
        wave_row.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        wave_row.columnconfigure(1, weight=1)
        ttk.Label(wave_row, text="Wave").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.wave_choice = ttk.Combobox(wave_row, textvariable=self.wave_choice_var, state="readonly")
        self.wave_choice.grid(row=0, column=1, sticky="ew")
        self.wave_choice.bind("<<ComboboxSelected>>", lambda _e: self.refresh_recommendations())
        rec_buttons = ttk.Frame(recommend)
        rec_buttons.grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Button(rec_buttons, text="Use Recommendation", style="Accent.TButton", command=self.use_selected_recommendation).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(rec_buttons, text="Open Recommendation", style="Ghost.TButton", command=self.open_selected_recommendation).grid(row=0, column=1)

        lyrics = ttk.Frame(right, style="Card.TFrame", padding=16)
        lyrics.grid(row=2, column=0, sticky="nsew")
        lyrics.columnconfigure(0, weight=1)
        lyrics.columnconfigure(1, weight=1)
        lyrics.rowconfigure(2, weight=1)
        ttk.Label(lyrics, text="Lyrics Sync", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(lyrics, textvariable=self.timecode_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Label(lyrics, textvariable=self.lyrics_status_var, style="Muted.TLabel", wraplength=420).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 10))
        self.lyrics_list = tk.Listbox(lyrics)
        self.style_listbox(self.lyrics_list)
        self.lyrics_list.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        editor_box = ttk.Frame(lyrics, style="Inset.TFrame", padding=6)
        editor_box.grid(row=2, column=1, sticky="nsew")
        editor_box.rowconfigure(0, weight=1)
        editor_box.columnconfigure(0, weight=1)
        self.lyrics_editor = tk.Text(editor_box, wrap="word", height=14, padx=10, pady=10)
        self.style_text(self.lyrics_editor)
        self.lyrics_editor.grid(row=0, column=0, sticky="nsew")
        lyric_buttons = ttk.Frame(lyrics)
        lyric_buttons.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(lyric_buttons, text="Save Timecodes", style="Accent.TButton", command=self.save_lyrics_for_current_track).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(lyric_buttons, text="Insert Current Time", style="Ghost.TButton", command=self.insert_current_timecode).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(lyric_buttons, text="Clear Text", style="Ghost.TButton", command=self.clear_lyrics_editor).grid(row=0, column=2)

    def build_library_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")

        tracks_tab = ttk.Frame(notebook, padding=12)
        favorites_tab = ttk.Frame(notebook, padding=12)
        playlists_tab = ttk.Frame(notebook, padding=12)
        notebook.add(tracks_tab, text="Tracks")
        notebook.add(favorites_tab, text="Favorites")
        notebook.add(playlists_tab, text="Playlists")

        tracks_tab.columnconfigure(0, weight=1)
        tracks_tab.rowconfigure(1, weight=1)
        tracks_card = ttk.Frame(tracks_tab, style="Card.TFrame", padding=16)
        tracks_card.grid(row=0, column=0, sticky="nsew")
        tracks_card.columnconfigure(0, weight=1)
        tracks_card.rowconfigure(1, weight=1)
        ttk.Label(tracks_card, text="Library Tracks", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.library_browser_tree = ttk.Treeview(tracks_card, columns=("title", "source", "fav"), show="headings", selectmode="browse")
        self.library_browser_tree.heading("title", text="Track")
        self.library_browser_tree.heading("source", text="Source")
        self.library_browser_tree.heading("fav", text="Fav")
        self.library_browser_tree.column("fav", width=60, anchor="center")
        self.library_browser_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.library_browser_tree.bind("<<TreeviewSelect>>", self.on_library_browser_select)
        track_actions = ttk.Frame(tracks_card)
        track_actions.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(track_actions, text="Import", style="Ghost.TButton", command=self.import_tracks).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(track_actions, text="Play Selected", style="Accent.TButton", command=self.play_selected_library_track).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(track_actions, text="Toggle Favorite", style="Ghost.TButton", command=self.toggle_selected_library_favorite).grid(row=0, column=2, padx=(0, 8))
        self.library_playlist_choice = ttk.Combobox(track_actions, textvariable=self.playlist_choice_var, state="readonly", width=18)
        self.library_playlist_choice.grid(row=0, column=3, padx=(0, 8))
        ttk.Button(track_actions, text="Add To Playlist", style="Ghost.TButton", command=self.add_selected_track_to_playlist).grid(row=0, column=4)

        favorites_tab.columnconfigure(0, weight=1)
        favorites_tab.rowconfigure(0, weight=1)
        fav_card = ttk.Frame(favorites_tab, style="Card.TFrame", padding=16)
        fav_card.grid(row=0, column=0, sticky="nsew")
        fav_card.columnconfigure(0, weight=1)
        fav_card.rowconfigure(1, weight=1)
        ttk.Label(fav_card, text="Favourite Tracks", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.favorite_tracks_list = tk.Listbox(fav_card)
        self.style_listbox(self.favorite_tracks_list)
        self.favorite_tracks_list.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        fav_actions = ttk.Frame(fav_card)
        fav_actions.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(fav_actions, text="Play Favorite", style="Accent.TButton", command=self.play_selected_favorite).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(fav_actions, text="Remove Favorite", style="Ghost.TButton", command=self.remove_selected_favorite).grid(row=0, column=1)

        playlists_tab.columnconfigure(0, weight=1)
        playlists_tab.columnconfigure(1, weight=1)
        playlists_tab.rowconfigure(0, weight=1)
        playlist_card = ttk.Frame(playlists_tab, style="Card.TFrame", padding=16)
        playlist_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        playlist_card.columnconfigure(0, weight=1)
        playlist_card.rowconfigure(3, weight=1)
        ttk.Label(playlist_card, text="Playlists", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(playlist_card, textvariable=self.playlist_name_var).grid(row=1, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(playlist_card, text="Create Playlist", style="Accent.TButton", command=self.create_playlist_from_entry).grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.playlist_list = tk.Listbox(playlist_card)
        self.style_listbox(self.playlist_list)
        self.playlist_list.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        self.playlist_list.bind("<<ListboxSelect>>", self.on_playlist_select)

        playlist_tracks_card = ttk.Frame(playlists_tab, style="Card.TFrame", padding=16)
        playlist_tracks_card.grid(row=0, column=1, sticky="nsew")
        playlist_tracks_card.columnconfigure(0, weight=1)
        playlist_tracks_card.rowconfigure(1, weight=1)
        ttk.Label(playlist_tracks_card, text="Playlist Tracks", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.playlist_tracks_list = tk.Listbox(playlist_tracks_card)
        self.style_listbox(self.playlist_tracks_list)
        self.playlist_tracks_list.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        playlist_actions = ttk.Frame(playlist_tracks_card)
        playlist_actions.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(playlist_actions, text="Add Current Track", style="Ghost.TButton", command=self.add_current_track_to_playlist).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(playlist_actions, text="Play Selected", style="Accent.TButton", command=self.play_selected_playlist_track).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(playlist_actions, text="Remove Selected", style="Ghost.TButton", command=self.remove_selected_playlist_track).grid(row=0, column=2)

    def build_recommendations_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        rec_card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        rec_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        rec_card.columnconfigure(0, weight=1)
        rec_card.rowconfigure(2, weight=1)
        ttk.Label(rec_card, text="Recommendations", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(rec_card, textvariable=self.recommendation_reason_var, style="Muted.TLabel", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 10))
        self.recommendation_browser_list = tk.Listbox(rec_card)
        self.style_listbox(self.recommendation_browser_list)
        self.recommendation_browser_list.grid(row=2, column=0, sticky="nsew")
        self.recommendation_browser_list.bind("<<ListboxSelect>>", self.on_recommendation_select)
        rec_actions = ttk.Frame(rec_card)
        rec_actions.grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Button(rec_actions, text="Use Recommendation", style="Accent.TButton", command=self.use_selected_recommendation).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(rec_actions, text="Open Recommendation", style="Ghost.TButton", command=self.open_selected_recommendation).grid(row=0, column=1)

        side = ttk.Frame(parent)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)

        wave_card = ttk.Frame(side, style="Card.TFrame", padding=16)
        wave_card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        ttk.Label(wave_card, text="Wave Filter", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(wave_card, text="Active wave", style="Micro.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 6))
        self.recommendation_wave_choice = ttk.Combobox(wave_card, textvariable=self.wave_choice_var, state="readonly")
        self.recommendation_wave_choice.grid(row=2, column=0, sticky="ew")
        self.recommendation_wave_choice.bind("<<ComboboxSelected>>", lambda _e: self.refresh_recommendations())
        ttk.Label(wave_card, text="Name", style="Micro.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 6))
        ttk.Entry(wave_card, textvariable=self.wave_name_var).grid(row=4, column=0, sticky="ew")
        ttk.Label(wave_card, text="Keywords / vibe", style="Micro.TLabel").grid(row=5, column=0, sticky="w", pady=(12, 6))
        ttk.Entry(wave_card, textvariable=self.wave_keywords_var).grid(row=6, column=0, sticky="ew")
        ttk.Button(wave_card, text="Save Wave", style="Accent.TButton", command=self.save_wave_profile).grid(row=7, column=0, sticky="w", pady=(12, 0))

        hint_card = ttk.Frame(side, style="Card.TFrame", padding=16)
        hint_card.grid(row=1, column=0, sticky="nsew")
        ttk.Label(hint_card, text="Foundation", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hint_card,
            text="Recommendations use tracks you played before, repeated keywords in your library, and your own saved wave presets.",
            style="Muted.TLabel",
            wraplength=380,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

    def build_options_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=2)
        parent.columnconfigure(1, weight=3)
        parent.rowconfigure(1, weight=1)

        prefs = ttk.Frame(parent, style="Card.TFrame", padding=16)
        prefs.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        ttk.Label(prefs, text=self.ui["options"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(prefs, text=self.ui["language"], style="Micro.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 6))
        ttk.Combobox(prefs, textvariable=self.language_var, values=["en", "ru"], state="readonly", width=18).grid(row=2, column=0, sticky="w")
        ttk.Label(prefs, text=self.ui["equalizer"], style="Micro.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 6))
        eq_mode = ttk.Combobox(prefs, textvariable=self.eq_var, values=list(EQ_PRESETS.keys()), state="readonly", width=20)
        eq_mode.grid(row=4, column=0, sticky="w")
        eq_mode.bind("<<ComboboxSelected>>", lambda _e: self.save_audio())
        ttk.Label(prefs, text=self.ui["speed"], style="Micro.TLabel").grid(row=5, column=0, sticky="w", pady=(12, 6))
        speed_mode = ttk.Combobox(prefs, textvariable=self.speed_var, values=list(SPEED_PRESETS.keys()), state="readonly", width=20)
        speed_mode.grid(row=6, column=0, sticky="w")
        speed_mode.bind("<<ComboboxSelected>>", lambda _e: self.save_audio())
        eq_box = ttk.Frame(prefs, style="Inset.TFrame", padding=12)
        eq_box.grid(row=7, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(eq_box, text="Hand Custom EQ", style="Head.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(eq_box, text="Low", style="Micro.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(eq_box, text="Mid", style="Micro.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Label(eq_box, text="High", style="Micro.TLabel").grid(row=1, column=2, sticky="w")
        tk.Scale(eq_box, from_=-10, to=10, orient="vertical", variable=self.eq_low_var, command=self.on_eq_slider_change, bg=SURFACE_ALT, fg=TEXT, highlightthickness=0, troughcolor=INPUT_BG, activebackground=ACCENT, relief="flat").grid(row=2, column=0, padx=(0, 10))
        tk.Scale(eq_box, from_=-10, to=10, orient="vertical", variable=self.eq_mid_var, command=self.on_eq_slider_change, bg=SURFACE_ALT, fg=TEXT, highlightthickness=0, troughcolor=INPUT_BG, activebackground=ACCENT, relief="flat").grid(row=2, column=1, padx=(0, 10))
        tk.Scale(eq_box, from_=-10, to=10, orient="vertical", variable=self.eq_high_var, command=self.on_eq_slider_change, bg=SURFACE_ALT, fg=TEXT, highlightthickness=0, troughcolor=INPUT_BG, activebackground=ACCENT, relief="flat").grid(row=2, column=2)
        ttk.Button(prefs, text=self.ui["save_settings"], style="Accent.TButton", command=self.save_preferences).grid(row=8, column=0, sticky="w", pady=(16, 0))

        wave = ttk.Frame(prefs, style="Inset.TFrame", padding=12)
        wave.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(wave, text="Own Wave", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(wave, text="Name", style="Micro.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 4))
        ttk.Entry(wave, textvariable=self.wave_name_var, width=24).grid(row=2, column=0, sticky="ew")
        ttk.Label(wave, text="Keywords / vibe", style="Micro.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 4))
        ttk.Entry(wave, textvariable=self.wave_keywords_var, width=28).grid(row=4, column=0, sticky="ew")
        ttk.Button(wave, text="Save Wave", style="Accent.TButton", command=self.save_wave_profile).grid(row=5, column=0, sticky="w", pady=(12, 0))

        bg = ttk.Frame(parent, style="Card.TFrame", padding=16)
        bg.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        bg.columnconfigure(0, weight=1)
        ttk.Label(bg, text=self.ui["backgrounds"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(bg, text="The interface is already styled from your references. This panel only controls the user background layer.", style="CardBody.TLabel", wraplength=560).grid(row=1, column=0, sticky="w", pady=(6, 0))
        feature_row = ttk.Frame(bg, style="Inset.TFrame", padding=12)
        feature_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        feature_row.columnconfigure(0, weight=1)
        feature_row.columnconfigure(1, weight=1)
        summary_a = ttk.Frame(feature_row, style="Inset.TFrame", padding=10)
        summary_a.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(summary_a, text="Visual Direction", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_a, text="Dark blue-black shell, cyan edges, soft contrast, and large product-like cards.", style="InsetBody.TLabel", wraplength=250).grid(row=1, column=0, sticky="w", pady=(6, 0))
        summary_b = ttk.Frame(feature_row, style="Inset.TFrame", padding=10)
        summary_b.grid(row=0, column=1, sticky="nsew")
        ttk.Label(summary_b, text="Background Layer", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_b, text="Upload a photo, GIF, or direct image source to personalize the scene behind the app.", style="InsetBody.TLabel", wraplength=250).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(bg, textvariable=self.bg_var).grid(row=3, column=0, sticky="ew", pady=(12, 0))
        row = ttk.Frame(bg)
        row.grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Button(row, text=self.ui["choose_file"], style="Ghost.TButton", command=self.choose_background).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(row, text=self.ui["apply_source"], style="Accent.TButton", command=self.apply_background).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(row, text=self.ui["reset_background"], style="Ghost.TButton", command=self.reset_background).grid(row=0, column=2)
        self.bg_label = tk.Label(bg, bg=INPUT_BG, fg=MUTED, text=self.ui["server_note"], width=58, height=10)
        self.bg_label.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
        ttk.Label(bg, text=self.ui["server_note"], style="Muted.TLabel", wraplength=560).grid(row=6, column=0, sticky="w", pady=(12, 0))
        js_eq = ttk.Frame(bg, style="Inset.TFrame", padding=12)
        js_eq.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        ttk.Label(js_eq, text="Imported JS Equalizer", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            js_eq,
            text="Open the standalone JavaScript equalizer from inside the app. It uses the Web Audio API and local audio files.",
            style="Muted.TLabel",
            wraplength=520,
        ).grid(row=1, column=0, sticky="w", pady=(6, 10))
        action_row = ttk.Frame(js_eq)
        action_row.grid(row=2, column=0, sticky="w")
        ttk.Button(action_row, text="Open JS Equalizer", style="Accent.TButton", command=self.open_imported_equalizer).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_row, text="Open Embed Portal", style="Ghost.TButton", command=self.open_embed_portal).grid(row=0, column=1)

        tokens = ttk.Frame(parent, style="Card.TFrame", padding=16)
        tokens.grid(row=1, column=0, columnspan=2, sticky="nsew")
        ttk.Label(tokens, text=self.ui["tokens"], style="Head.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        for index, (field, label) in enumerate(TOKEN_FIELDS):
            col = index % 2
            row_index = index // 2 * 2 + 1
            ttk.Label(tokens, text=label, style="Micro.TLabel").grid(row=row_index, column=col, sticky="w", padx=(0, 12), pady=(12, 0))
            ttk.Entry(tokens, textvariable=self.token_vars[field], width=44).grid(row=row_index + 1, column=col, sticky="ew", padx=(0, 12))
        ttk.Button(tokens, text=self.ui["save_tokens"], style="Accent.TButton", command=self.save_tokens).grid(row=7, column=0, sticky="w", pady=(16, 0))

    def build_arcade_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)

        spots = ttk.Frame(parent, style="Card.TFrame", padding=16)
        spots.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.spots_var = tk.StringVar()
        self.spots_best_var = tk.StringVar()
        ttk.Label(spots, text=self.ui["mini_spots"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(spots, textvariable=self.spots_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")
        self.spots_canvas = tk.Canvas(spots, width=320, height=260)
        self.style_canvas(self.spots_canvas)
        self.spots_canvas.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        ttk.Label(spots, textvariable=self.spots_best_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(spots, text=self.ui["start"], style="Accent.TButton", command=self.start_spots).grid(row=2, column=1, sticky="e", pady=(12, 0))

        snake = ttk.Frame(parent, style="Card.TFrame", padding=16)
        snake.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self.snake_var = tk.StringVar()
        self.snake_best_var = tk.StringVar()
        ttk.Label(snake, text=self.ui["mini_snake"], style="Head.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(snake, textvariable=self.snake_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")
        self.snake_canvas = tk.Canvas(snake, width=288, height=288)
        self.style_canvas(self.snake_canvas)
        self.snake_canvas.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        ttk.Label(snake, textvariable=self.snake_best_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(snake, text=self.ui["start"], style="Accent.TButton", command=self.start_snake).grid(row=2, column=1, sticky="e", pady=(12, 0))

        calc = ttk.Frame(parent, style="Card.TFrame", padding=16)
        calc.grid(row=0, column=2, sticky="nsew")
        for column in range(4):
            calc.columnconfigure(column, weight=1)
        ttk.Label(calc, text=self.ui["mini_calc"], style="Head.TLabel").grid(row=0, column=0, sticky="w", columnspan=2)
        ttk.Label(calc, text="Clean display", style="Muted.TLabel").grid(row=0, column=2, columnspan=2, sticky="e")
        display_box = ttk.Frame(calc, style="Inset.TFrame", padding=10)
        display_box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(12, 12))
        display_box.columnconfigure(0, weight=1)
        tk.Label(display_box, textvariable=self.calc_history_var, bg=SURFACE_ALT, fg=MUTED, anchor="e", padx=6, pady=2, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="ew")
        self.calc_display = tk.Entry(
            display_box,
            textvariable=self.calc_var,
            justify="right",
            relief="flat",
            bd=0,
            bg=INPUT_BG,
            fg=TEXT,
            readonlybackground=INPUT_BG,
            insertbackground=TEXT,
            font=("Bahnschrift", 24, "bold"),
        )
        self.calc_display.grid(row=1, column=0, sticky="ew", pady=(6, 0), ipady=10)
        self.calc_display.configure(state="readonly")
        buttons = [
            [("%", "%"), ("CE", "CE"), ("C", "C"), ("⌫", "BACK")],
            [("1/x", "RECIP"), ("x²", "SQUARE"), ("√x", "SQRT"), ("÷", "/")],
            [("7", "7"), ("8", "8"), ("9", "9"), ("×", "*")],
            [("4", "4"), ("5", "5"), ("6", "6"), ("−", "-")],
            [("1", "1"), ("2", "2"), ("3", "3"), ("+", "+")],
            [("+/−", "NEG"), ("0", "0"), (".", "."), ("=", "=")],
        ]
        action_tokens = {"=", "/", "*", "-", "+"}
        utility_tokens = {"BACK", "CE", "C", "RECIP", "SQUARE", "SQRT", "NEG", "%"}
        for row_index, row in enumerate(buttons, start=2):
            calc.rowconfigure(row_index, weight=1)
            for col_index, (label, token) in enumerate(row):
                bg_color = ACCENT_STRONG if token in action_tokens else SURFACE_ALT
                if token in utility_tokens:
                    bg_color = "#122634"
                button = tk.Button(
                    calc,
                    text=label,
                    bg=bg_color,
                    fg=TEXT,
                    relief="flat",
                    bd=0,
                    font=("Bahnschrift", 13, "bold"),
                    activebackground=ACCENT if token in action_tokens else "#1a3141",
                    activeforeground=TEXT,
                    command=lambda value=token: self.on_calc_press(value),
                )
                button.grid(row=row_index, column=col_index, sticky="nsew", padx=4, pady=4, ipady=12)

    def refresh_all(self) -> None:
        self.state = load_state()
        self.eq_var.set(self.state.get("eq_preset", self.eq_var.get()))
        self.speed_var.set(self.state.get("speed_preset", self.speed_var.get()))
        custom_eq = self.state.get("custom_eq", {})
        self.eq_low_var.set(int(custom_eq.get("low", self.eq_low_var.get())))
        self.eq_mid_var.set(int(custom_eq.get("mid", self.eq_mid_var.get())))
        self.eq_high_var.set(int(custom_eq.get("high", self.eq_high_var.get())))
        current = self.state.get("current_track")
        self.track_var.set(f"{current.get('title', '')} | {current.get('source', '')}" if current else "No track selected")
        for row in self.library_tree.get_children():
            self.library_tree.delete(row)
        for index, item in enumerate(self.state.get("library", [])):
            self.library_tree.insert("", "end", iid=str(index), values=(item.get("title", ""), item.get("source", "")))
        self.refresh_library_views()
        if current:
            self.engine.load(str(current.get("path", "")))
        self.engine.apply(
            self.eq_var.get(),
            self.speed_var.get(),
            {"low": self.eq_low_var.get(), "mid": self.eq_mid_var.get(), "high": self.eq_high_var.get()},
        )
        self.refresh_background_preview()
        self.load_lyrics_for_current_track()
        self.refresh_recommendations()
        mode = self.ui["status_demo"] if not self.engine.available else "Playback enabled"
        self.status_var.set(f"{mode}. {self.server_status}")
        self.refresh_scores()

    def refresh_scores(self) -> None:
        self.spots_var.set(f"{self.ui['score']}: {self.spots_score}")
        self.spots_best_var.set(f"{self.ui['best']}: {self.spots_best}")
        self.snake_var.set(f"{self.ui['score']}: {self.snake_score}")
        self.snake_best_var.set(f"{self.ui['best']}: {self.snake_best}")

    def refresh_recommendations(self) -> None:
        if not self.recommendation_list and not self.recommendation_browser_list:
            return
        foundation = build_recommendation_foundation(self.state, self.wave_choice_var.get())
        self.recommendation_items = foundation["suggestions"]
        playlist_names = [item.get("name", "") for item in self.state.get("playlists", [])]
        for widget in (self.recommendation_list, self.recommendation_browser_list):
            if widget:
                widget.delete(0, "end")
                for item in self.recommendation_items:
                    widget.insert("end", item["label"])
        wave_names = [wave["name"] for wave in foundation["waves"]]
        self.wave_choice["values"] = wave_names
        if hasattr(self, "library_playlist_choice"):
            self.library_playlist_choice["values"] = playlist_names
        if hasattr(self, "recommendation_wave_choice"):
            self.recommendation_wave_choice["values"] = wave_names
        if wave_names and self.wave_choice_var.get() not in wave_names:
            self.wave_choice_var.set(wave_names[0])
        if foundation["active_wave"]:
            self.wave_name_var.set(foundation["active_wave"]["name"])
            self.wave_keywords_var.set(foundation["active_wave"]["keywords"])
        if foundation["top_keywords"]:
            self.recommendation_reason_var.set(
                "History keywords: " + ", ".join(foundation["top_keywords"][:4])
            )
        elif foundation["recent_titles"]:
            self.recommendation_reason_var.set(
                "Recent tracks: " + ", ".join(foundation["recent_titles"][:3])
            )
        else:
            self.recommendation_reason_var.set("Play a few local tracks or save a wave to build recommendations.")

    def refresh_library_views(self) -> None:
        library = self.state.get("library", [])
        if self.library_browser_tree:
            for row in self.library_browser_tree.get_children():
                self.library_browser_tree.delete(row)
            for index, item in enumerate(library):
                self.library_browser_tree.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(item.get("title", ""), item.get("source", ""), "★" if is_favorite(self.state, item) else ""),
                )
        if self.favorite_tracks_list:
            self.favorite_tracks_list.delete(0, "end")
            for item in library:
                if is_favorite(self.state, item):
                    self.favorite_tracks_list.insert("end", item.get("title", ""))
        playlist_names = [playlist.get("name", "") for playlist in self.state.get("playlists", [])]
        if hasattr(self, "library_playlist_choice"):
            self.library_playlist_choice["values"] = playlist_names
        if self.playlist_list:
            self.playlist_list.delete(0, "end")
            for name in playlist_names:
                self.playlist_list.insert("end", name)
        if self.playlist_choice_var.get() not in playlist_names:
            self.playlist_choice_var.set(playlist_names[0] if playlist_names else "")
        self.refresh_selected_playlist_tracks()

    def refresh_selected_playlist_tracks(self) -> None:
        if not self.playlist_tracks_list:
            return
        self.playlist_tracks_list.delete(0, "end")
        self.playlist_tracks_keys = []
        selected = self.get_selected_playlist_name()
        if not selected:
            return
        tracks_by_key = {get_track_key(item): item for item in self.state.get("library", [])}
        for playlist in self.state.get("playlists", []):
            if playlist.get("name") == selected:
                for key in playlist.get("tracks", []):
                    track = tracks_by_key.get(key)
                    if track:
                        self.playlist_tracks_keys.append(key)
                        self.playlist_tracks_list.insert("end", track.get("title", ""))
                return

    def on_recommendation_select(self, _event=None) -> None:
        source = None
        if self.recommendation_browser_list and self.recommendation_browser_list.curselection():
            source = self.recommendation_browser_list
        elif self.recommendation_list and self.recommendation_list.curselection():
            source = self.recommendation_list
        if not source:
            return
        selection = source.curselection()
        if not selection or not self.recommendation_items:
            return
        item = self.recommendation_items[selection[0]]
        self.recommendation_reason_var.set(f"{item['reason']} -> {item['query']}")

    def use_selected_recommendation(self) -> None:
        selection = ()
        if self.recommendation_browser_list and self.recommendation_browser_list.curselection():
            selection = self.recommendation_browser_list.curselection()
        elif self.recommendation_list and self.recommendation_list.curselection():
            selection = self.recommendation_list.curselection()
        if not selection or not self.recommendation_items:
            return
        item = self.recommendation_items[selection[0]]
        self.search_var.set(item["query"])
        self.search_everywhere()

    def open_selected_recommendation(self) -> None:
        self.use_selected_recommendation()
        if self.search_results:
            self.open_embedded_window(self.search_results[0]["url"])

    def get_track_by_key(self, track_key: str) -> tuple[int, dict] | tuple[None, None]:
        for index, item in enumerate(self.state.get("library", [])):
            if get_track_key(item) == track_key:
                return index, item
        return None, None

    def select_track_by_key(self, track_key: str, auto_play: bool = False) -> None:
        index, _track = self.get_track_by_key(track_key)
        if index is None:
            return
        set_current_track(self.state, index)
        save_state(self.state)
        self.refresh_all()
        if auto_play:
            self.play_current()

    def on_library_browser_select(self, _event=None) -> None:
        if not self.library_browser_tree:
            return
        selection = self.library_browser_tree.selection()
        if not selection:
            return
        set_current_track(self.state, int(selection[0]))
        save_state(self.state)
        self.refresh_all()

    def play_selected_library_track(self) -> None:
        if not self.library_browser_tree:
            return
        selection = self.library_browser_tree.selection()
        if not selection:
            return
        set_current_track(self.state, int(selection[0]))
        save_state(self.state)
        self.refresh_all()
        self.play_current()

    def toggle_selected_library_favorite(self) -> None:
        target = self.state.get("current_track")
        if self.library_browser_tree and self.library_browser_tree.selection():
            target = self.state["library"][int(self.library_browser_tree.selection()[0])]
        if not target:
            return
        toggle_favorite(self.state, target)
        save_state(self.state)
        self.refresh_all()

    def play_selected_favorite(self) -> None:
        if not self.favorite_tracks_list:
            return
        selection = self.favorite_tracks_list.curselection()
        if not selection:
            return
        favorite_titles = [
            item for item in self.state.get("library", []) if is_favorite(self.state, item)
        ]
        if selection[0] < len(favorite_titles):
            self.select_track_by_key(get_track_key(favorite_titles[selection[0]]), auto_play=True)

    def remove_selected_favorite(self) -> None:
        if not self.favorite_tracks_list:
            return
        selection = self.favorite_tracks_list.curselection()
        if not selection:
            return
        favorite_tracks = [item for item in self.state.get("library", []) if is_favorite(self.state, item)]
        if selection[0] < len(favorite_tracks):
            toggle_favorite(self.state, favorite_tracks[selection[0]])
            save_state(self.state)
            self.refresh_all()

    def create_playlist_from_entry(self) -> None:
        try:
            create_playlist(self.state, self.playlist_name_var.get())
        except ValueError as exc:
            messagebox.showerror("Playlist", str(exc))
            return
        save_state(self.state)
        self.playlist_choice_var.set(self.playlist_name_var.get().strip())
        self.playlist_name_var.set("")
        self.refresh_all()

    def get_selected_playlist_name(self) -> str:
        if self.playlist_list and self.playlist_list.curselection():
            return self.playlist_list.get(self.playlist_list.curselection()[0])
        return self.playlist_choice_var.get().strip()

    def on_playlist_select(self, _event=None) -> None:
        if self.playlist_list and self.playlist_list.curselection():
            self.playlist_choice_var.set(self.playlist_list.get(self.playlist_list.curselection()[0]))
        self.refresh_selected_playlist_tracks()

    def add_selected_track_to_playlist(self) -> None:
        target = self.state.get("current_track")
        if self.library_browser_tree and self.library_browser_tree.selection():
            target = self.state["library"][int(self.library_browser_tree.selection()[0])]
        if not target:
            return
        try:
            add_track_to_playlist(self.state, self.playlist_choice_var.get(), target)
        except ValueError as exc:
            messagebox.showerror("Playlist", str(exc))
            return
        save_state(self.state)
        self.refresh_all()

    def add_current_track_to_playlist(self) -> None:
        target = self.state.get("current_track")
        if not target:
            return
        try:
            add_track_to_playlist(self.state, self.get_selected_playlist_name(), target)
        except ValueError as exc:
            messagebox.showerror("Playlist", str(exc))
            return
        save_state(self.state)
        self.refresh_all()

    def play_selected_playlist_track(self) -> None:
        if not self.playlist_tracks_list:
            return
        selection = self.playlist_tracks_list.curselection()
        if not selection or selection[0] >= len(self.playlist_tracks_keys):
            return
        self.select_track_by_key(self.playlist_tracks_keys[selection[0]], auto_play=True)

    def remove_selected_playlist_track(self) -> None:
        if not self.playlist_tracks_list:
            return
        selection = self.playlist_tracks_list.curselection()
        playlist_name = self.get_selected_playlist_name()
        if not selection or selection[0] >= len(self.playlist_tracks_keys) or not playlist_name:
            return
        remove_track_from_playlist(self.state, playlist_name, self.playlist_tracks_keys[selection[0]])
        save_state(self.state)
        self.refresh_all()

    def on_eq_slider_change(self, _value=None) -> None:
        self.eq_var.set("Custom")
        self.state["custom_eq"] = {
            "low": self.eq_low_var.get(),
            "mid": self.eq_mid_var.get(),
            "high": self.eq_high_var.get(),
        }
        self.save_audio()

    def save_audio(self) -> None:
        self.state["eq_preset"] = self.eq_var.get()
        self.state["speed_preset"] = self.speed_var.get()
        if self.eq_var.get() != "Custom":
            preset = EQ_PRESETS.get(self.eq_var.get(), EQ_PRESETS["Flat"])
            self.eq_low_var.set(int(preset["low"]))
            self.eq_mid_var.set(int(preset["mid"]))
            self.eq_high_var.set(int(preset["high"]))
        self.state["custom_eq"] = {
            "low": self.eq_low_var.get(),
            "mid": self.eq_mid_var.get(),
            "high": self.eq_high_var.get(),
        }
        save_state(self.state)
        self.engine.apply(self.eq_var.get(), self.speed_var.get(), self.state["custom_eq"])

    def save_preferences(self) -> None:
        self.state["language"] = self.language_var.get() if self.language_var.get() in {"en", "ru"} else "en"
        self.state["eq_preset"] = self.eq_var.get()
        self.state["speed_preset"] = self.speed_var.get()
        save_state(self.state)
        messagebox.showinfo(self.ui["options"], "Restart the app to fully reload all labels.")

    def save_wave_profile(self) -> None:
        try:
            save_custom_wave(self.state, self.wave_name_var.get(), self.wave_keywords_var.get())
        except ValueError as exc:
            messagebox.showerror("Own Wave", str(exc))
            return
        save_state(self.state)
        self.refresh_recommendations()
        messagebox.showinfo("Own Wave", "Wave saved and included in recommendation foundation.")

    def save_tokens(self) -> None:
        for field in self.token_vars:
            self.state["tokens"][field] = self.token_vars[field].get().strip()
        save_state(self.state)
        messagebox.showinfo(self.ui["tokens"], self.ui["save_tokens"])

    def open_imported_equalizer(self) -> None:
        if not JS_EQUALIZER_PAGE.exists():
            messagebox.showerror("JS Equalizer", f"File not found: {JS_EQUALIZER_PAGE}")
            return
        webbrowser.open(JS_EQUALIZER_PAGE.resolve().as_uri())

    def open_embedded_window(self, target_url: str) -> None:
        if not EMBED_PLAYER_HELPER.exists():
            webbrowser.open(target_url)
            return
        subprocess.Popen(
            [sys.executable, str(EMBED_PLAYER_HELPER), target_url],
            cwd=str(APP_DIR),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def open_embed_portal(self, content_url: str = "") -> None:
        if not EMBED_PORTAL_PAGE.exists():
            messagebox.showerror("Embedded Player", f"File not found: {EMBED_PORTAL_PAGE}")
            return
        base = EMBED_PORTAL_PAGE.resolve().as_uri()
        target = f"{base}?url={quote_plus(content_url)}" if content_url else base
        self.open_embedded_window(target)

    def choose_background(self) -> None:
        selected = filedialog.askopenfilename(title=self.ui["choose_file"], filetypes=[("Images", "*.png *.gif *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if selected:
            self.bg_var.set(selected)

    def apply_background(self) -> None:
        try:
            imported_name = import_background_source(self.bg_var.get())
        except Exception as exc:
            messagebox.showerror(self.ui["backgrounds"], str(exc))
            return
        self.state["background"] = {"type": "upload", "value": imported_name}
        save_state(self.state)
        self.refresh_background_preview()

    def reset_background(self) -> None:
        self.state["background"] = {"type": "gradient", "value": ""}
        save_state(self.state)
        self.refresh_background_preview()

    def resize_photo(self, image: tk.PhotoImage, max_width: int = 420, max_height: int = 240) -> tk.PhotoImage:
        ratio = max((image.width() + max_width - 1) // max_width, (image.height() + max_height - 1) // max_height, 1)
        return image.subsample(ratio, ratio) if ratio > 1 else image

    def animate_bg(self, index: int = 0) -> None:
        if not self.bg_label or not self.bg_frames:
            return
        self.bg_label.configure(image=self.bg_frames[index], text="")
        self.bg_label.image = self.bg_frames[index]
        self.bg_job = self.root.after(120, lambda: self.animate_bg((index + 1) % len(self.bg_frames)))

    def refresh_background_preview(self) -> None:
        if self.bg_job:
            self.root.after_cancel(self.bg_job)
            self.bg_job = None
        self.bg_frames = []
        self.bg_static = None
        path = resolve_background_path(self.state)
        if not self.bg_label:
            return
        if not path:
            self.bg_label.configure(image="", text="Animated gradient mode", bg="#08172b", fg=MUTED)
            self.bg_label.image = None
            return
        try:
            if path.suffix.lower() == ".gif":
                frames = []
                index = 0
                while True:
                    try:
                        frames.append(self.resize_photo(tk.PhotoImage(file=str(path), format=f"gif -index {index}")))
                        index += 1
                    except tk.TclError:
                        break
                if frames:
                    self.bg_frames = frames
                    self.animate_bg()
                    return
            self.bg_static = self.resize_photo(tk.PhotoImage(file=str(path)))
            self.bg_label.configure(image=self.bg_static, text="")
            self.bg_label.image = self.bg_static
        except tk.TclError:
            self.bg_label.configure(image="", text=path.name, bg="#08172b", fg=MUTED)
            self.bg_label.image = None

    def format_timecode(self, milliseconds: int) -> str:
        total = max(milliseconds, 0)
        minutes = total // 60000
        seconds = (total % 60000) // 1000
        centiseconds = (total % 1000) // 10
        return f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    def parse_timecoded_text(self, raw_text: str) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []
        timestamp_pattern = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            matches = list(timestamp_pattern.finditer(line))
            if not matches:
                continue
            text = timestamp_pattern.sub("", line).strip() or "..."
            for match in matches:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                fraction = match.group(3) or "0"
                if len(fraction) == 1:
                    fraction_ms = int(fraction) * 100
                elif len(fraction) == 2:
                    fraction_ms = int(fraction) * 10
                else:
                    fraction_ms = int(fraction[:3])
                entries.append((minutes * 60000 + seconds * 1000 + fraction_ms, text))
        entries.sort(key=lambda item: item[0])
        return entries

    def load_lyrics_for_current_track(self) -> None:
        if not self.lyrics_editor or not self.lyrics_list:
            return
        track = self.state.get("current_track") or {}
        raw_text = str(track.get("lyrics_text", ""))
        self.lyrics_editor.delete("1.0", "end")
        self.lyrics_editor.insert("1.0", raw_text)
        self.lyrics_lines = self.parse_timecoded_text(raw_text)
        self.lyrics_list.delete(0, "end")
        for timestamp, line in self.lyrics_lines:
            self.lyrics_list.insert("end", f"[{self.format_timecode(timestamp)}] {line}")
        if self.lyrics_lines:
            self.lyrics_status_var.set(f"Loaded {len(self.lyrics_lines)} synced lines for the current track.")
        else:
            self.lyrics_status_var.set("Paste timecoded lines like [00:12.40] first lyric line.")
        self.active_lyric_index = None

    def save_lyrics_for_current_track(self) -> None:
        if not self.lyrics_editor:
            return
        current_index = self.state.get("current_track_index")
        if current_index is None:
            messagebox.showinfo("Lyrics Sync", "Select a local track first.")
            return
        raw_text = self.lyrics_editor.get("1.0", "end").strip()
        self.state["library"][current_index]["lyrics_text"] = raw_text
        set_current_track(self.state, current_index)
        save_state(self.state)
        self.load_lyrics_for_current_track()

    def insert_current_timecode(self) -> None:
        if not self.lyrics_editor:
            return
        current_ms = self.engine.get_time_ms() or 0
        marker = f"[{self.format_timecode(current_ms)}] "
        self.lyrics_editor.insert("insert", marker)
        self.lyrics_editor.focus_set()

    def clear_lyrics_editor(self) -> None:
        if self.lyrics_editor:
            self.lyrics_editor.delete("1.0", "end")
        self.lyrics_lines = []
        if self.lyrics_list:
            self.lyrics_list.delete(0, "end")
        self.active_lyric_index = None
        self.lyrics_status_var.set("Lyrics editor cleared. Save if you want to remove synced text from the track.")

    def highlight_lyrics_for_time(self, current_ms: int | None) -> None:
        if not self.lyrics_list:
            return
        if current_ms is None:
            self.timecode_var.set("00:00.00")
            return
        self.timecode_var.set(self.format_timecode(current_ms))
        target_index: int | None = None
        for index, (timestamp, _line) in enumerate(self.lyrics_lines):
            if current_ms >= timestamp:
                target_index = index
            else:
                break
        if target_index is None or target_index == self.active_lyric_index:
            return
        self.lyrics_list.selection_clear(0, "end")
        self.lyrics_list.selection_set(target_index)
        self.lyrics_list.activate(target_index)
        self.lyrics_list.see(target_index)
        self.active_lyric_index = target_index

    def schedule_lyrics_sync(self) -> None:
        self.highlight_lyrics_for_time(self.engine.get_time_ms())
        self.lyrics_job = self.root.after(250, self.schedule_lyrics_sync)

    def import_tracks(self) -> None:
        selected = filedialog.askopenfilenames(title=self.ui["import_tracks"], filetypes=[("Audio files", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("All files", "*.*")])
        if not selected:
            return
        added = 0
        for path in selected:
            try:
                self.state["library"].append(import_track_path(path))
                added += 1
            except Exception:
                continue
        if not added:
            messagebox.showerror(self.ui["import_tracks"], "No valid files were imported.")
            return
        set_current_track(self.state, len(self.state["library"]) - added)
        save_state(self.state)
        self.refresh_all()

    def on_library_select(self, _event=None) -> None:
        selected = self.library_tree.selection()
        if not selected:
            return
        set_current_track(self.state, int(selected[0]))
        save_state(self.state)
        self.refresh_all()

    def play_current(self) -> None:
        if not self.state.get("current_track"):
            messagebox.showinfo(self.ui["current_track"], self.ui["empty_library"])
            return
        record_play_event(self.state, self.state["current_track"])
        save_state(self.state)
        self.engine.play()
        self.refresh_recommendations()

    def search_everywhere(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            return
        self.search_results = build_search_results(query)
        self.result_list.delete(0, "end")
        for item in self.search_results:
            self.result_list.insert("end", f"{item['provider']}: {query}")

    def open_selected(self, key: str) -> None:
        if not self.search_results or not self.result_list.curselection():
            return
        target = self.search_results[self.result_list.curselection()[0]][key]
        if key == "url":
            self.open_embedded_window(target)
        else:
            webbrowser.open(target)

    def open_all_results(self) -> None:
        if not self.search_results:
            self.search_everywhere()
        for item in self.search_results:
            self.open_embedded_window(item["url"])

    def start_spots(self) -> None:
        self.stop_spots()
        self.spots_score = 0
        self.spawn_spot()
        self.spots_end_job = self.root.after(20000, self.stop_spots)
        self.refresh_scores()

    def spawn_spot(self) -> None:
        if not self.spots_canvas:
            return
        self.spots_canvas.delete("all")
        x = random.randint(20, 260)
        y = random.randint(20, 200)
        spot = self.spots_canvas.create_oval(x, y, x + 38, y + 38, fill="#6ca8ff", outline="")
        self.spots_canvas.tag_bind(spot, "<Button-1>", lambda _e: self.hit_spot())
        self.spots_job = self.root.after(850, self.spawn_spot)

    def hit_spot(self) -> None:
        self.spots_score += 1
        if self.spots_score > self.spots_best:
            self.spots_best = self.spots_score
        self.refresh_scores()
        self.spawn_spot()

    def stop_spots(self) -> None:
        if self.spots_job:
            self.root.after_cancel(self.spots_job)
            self.spots_job = None
        if self.spots_end_job:
            self.root.after_cancel(self.spots_end_job)
            self.spots_end_job = None
        if hasattr(self, "spots_canvas") and self.spots_canvas:
            self.spots_canvas.delete("all")

    def queue_dir(self, direction: tuple[int, int]) -> None:
        if direction[0] == -self.snake_dir[0] and direction[1] == -self.snake_dir[1]:
            return
        self.snake_next = direction

    def reset_snake(self) -> None:
        if self.snake_job:
            self.root.after_cancel(self.snake_job)
            self.snake_job = None
        self.snake = [(4, 8), (3, 8), (2, 8)]
        self.snake_dir = (1, 0)
        self.snake_next = (1, 0)
        self.snake_score = 0
        self.place_food()
        self.draw_snake()
        self.refresh_scores()

    def place_food(self) -> None:
        while True:
            point = (random.randint(0, 15), random.randint(0, 15))
            if point not in self.snake:
                self.food = point
                return

    def draw_snake(self) -> None:
        if not self.snake_canvas:
            return
        self.snake_canvas.delete("all")
        for x, y in self.snake:
            self.snake_canvas.create_rectangle(x * 18 + 2, y * 18 + 2, x * 18 + 16, y * 18 + 16, fill="#6ca8ff", outline="")
        self.snake_canvas.create_oval(self.food[0] * 18 + 3, self.food[1] * 18 + 3, self.food[0] * 18 + 15, self.food[1] * 18 + 15, fill="#8eefff", outline="")

    def start_snake(self) -> None:
        if not self.snake_job:
            self.tick_snake()

    def tick_snake(self) -> None:
        self.snake_dir = self.snake_next
        head = self.snake[0]
        nxt = (head[0] + self.snake_dir[0], head[1] + self.snake_dir[1])
        if nxt[0] < 0 or nxt[1] < 0 or nxt[0] > 15 or nxt[1] > 15 or nxt in self.snake:
            if self.snake_score > self.snake_best:
                self.snake_best = self.snake_score
            self.reset_snake()
            return
        self.snake.insert(0, nxt)
        if nxt == self.food:
            self.snake_score += 1
            if self.snake_score > self.snake_best:
                self.snake_best = self.snake_score
            self.place_food()
        else:
            self.snake.pop()
        self.draw_snake()
        self.refresh_scores()
        self.snake_job = self.root.after(150, self.tick_snake)

    def parse_calc_value(self) -> Decimal:
        try:
            return Decimal(self.calc_var.get())
        except InvalidOperation:
            return Decimal("0")

    def format_decimal(self, value: Decimal) -> str:
        normalized = value.normalize() if value == value.to_integral() else value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text if text not in {"", "-0"} else "0"

    def format_calc_operator(self, operator: str) -> str:
        return {"/": "÷", "*": "×", "-": "−", "+": "+"}.get(operator, operator)

    def reset_calculator(self) -> None:
        self.calc_var.set("0")
        self.calc_history_var.set("")
        self.calc_accumulator = None
        self.calc_pending_op = None
        self.calc_last_operand = None
        self.calc_new_entry = True

    def clear_entry(self) -> None:
        self.calc_var.set("0")
        self.calc_new_entry = True

    def append_calc_digit(self, token: str) -> None:
        current = self.calc_var.get()
        if self.calc_new_entry or current == "Error":
            if token == ".":
                self.calc_var.set("0.")
            else:
                self.calc_var.set(token)
            self.calc_new_entry = False
            return
        if token == "." and "." in current:
            return
        if current == "0" and token != ".":
            self.calc_var.set(token)
        else:
            self.calc_var.set(current + token)

    def apply_unary(self, op: str) -> None:
        value = self.parse_calc_value()
        try:
            if op == "RECIP":
                if value == 0:
                    raise ZeroDivisionError
                result = Decimal("1") / value
            elif op == "SQUARE":
                result = value * value
            elif op == "SQRT":
                if value < 0:
                    raise ValueError
                result = value.sqrt()
            else:
                return
        except Exception:
            self.calc_var.set("Error")
            self.calc_new_entry = True
            self.calc_history_var.set("")
            return
        self.calc_var.set(self.format_decimal(result))
        label = {"RECIP": "1/x", "SQUARE": "x²", "SQRT": "√x"}.get(op, op)
        self.calc_history_var.set(f"{label}({self.format_decimal(value)})")
        self.calc_new_entry = True

    def evaluate_pending(self, right_operand: Decimal) -> Decimal:
        left = self.calc_accumulator if self.calc_accumulator is not None else Decimal("0")
        op = self.calc_pending_op
        if op == "+":
            return left + right_operand
        if op == "-":
            return left - right_operand
        if op == "*":
            return left * right_operand
        if op == "/":
            if right_operand == 0:
                raise ZeroDivisionError
            return left / right_operand
        return right_operand

    def apply_percent(self) -> None:
        current = self.parse_calc_value()
        if self.calc_accumulator is not None and self.calc_pending_op:
            result = (self.calc_accumulator * current) / Decimal("100")
        else:
            result = current / Decimal("100")
        self.calc_var.set(self.format_decimal(result))
        self.calc_new_entry = True

    def handle_operator(self, operator: str) -> None:
        current = self.parse_calc_value()
        try:
            if self.calc_pending_op and not self.calc_new_entry:
                self.calc_accumulator = self.evaluate_pending(current)
                self.calc_var.set(self.format_decimal(self.calc_accumulator))
            elif self.calc_accumulator is None:
                self.calc_accumulator = current
        except Exception:
            self.calc_var.set("Error")
            self.calc_history_var.set("")
            self.calc_accumulator = None
            self.calc_pending_op = None
            self.calc_new_entry = True
            return
        self.calc_pending_op = operator
        self.calc_history_var.set(f"{self.format_decimal(self.calc_accumulator or Decimal('0'))} {self.format_calc_operator(operator)}")
        self.calc_new_entry = True

    def handle_equals(self) -> None:
        if not self.calc_pending_op:
            return
        current = self.parse_calc_value()
        try:
            result = self.evaluate_pending(current)
        except Exception:
            self.calc_var.set("Error")
            self.calc_history_var.set("")
            self.calc_accumulator = None
            self.calc_pending_op = None
            self.calc_new_entry = True
            return
        history = f"{self.format_decimal(self.calc_accumulator or Decimal('0'))} {self.format_calc_operator(self.calc_pending_op)} {self.format_decimal(current)} ="
        self.calc_var.set(self.format_decimal(result))
        self.calc_history_var.set(history)
        self.calc_accumulator = result
        self.calc_last_operand = current
        self.calc_pending_op = None
        self.calc_new_entry = True

    def backspace_calc(self) -> None:
        if self.calc_new_entry:
            return
        current = self.calc_var.get()
        if len(current) <= 1 or (current.startswith("-") and len(current) == 2):
            self.calc_var.set("0")
            self.calc_new_entry = True
            return
        self.calc_var.set(current[:-1])

    def on_calc_press(self, token: str) -> None:
        if token in "0123456789.":
            self.append_calc_digit(token)
            return
        if token == "C":
            self.reset_calculator()
            return
        if token == "CE":
            self.clear_entry()
            return
        if token == "BACK":
            self.backspace_calc()
            return
        if token == "NEG":
            value = self.parse_calc_value() * Decimal("-1")
            self.calc_var.set(self.format_decimal(value))
            return
        if token == "%":
            self.apply_percent()
            return
        if token in {"RECIP", "SQUARE", "SQRT"}:
            self.apply_unary(token)
            return
        if token in {"+", "-", "*", "/"}:
            self.handle_operator(token)
            return
        if token == "=":
            self.handle_equals()

    def on_close(self) -> None:
        self.stop_spots()
        if self.lyrics_job:
            self.root.after_cancel(self.lyrics_job)
            self.lyrics_job = None
        try:
            self.engine.stop()
        except Exception:
            pass
        if self.server:
            self.server.stop()
        self.root.destroy()

    def run(self) -> None:
        self.reset_snake()
        self.root.mainloop()
