"""SpeakEasy settings window — a clean dark-card layout.

Opened from the tray's "Settings" item. tkinter is main-thread-only, so this is
always invoked on the app's main loop (the tray callback enqueues a command;
main.py calls ``open_settings_window`` while pumping the Tk root) — never
directly from the pystray thread.

Built as a Toplevel on the app's existing root (Overlay owns the single tk.Tk),
so we don't create a second Tk instance.

The body scrolls (small laptop screens are shorter than the full settings
list); the Save/Cancel footer stays pinned outside the scroll area so it's
always reachable. Sizing comes from the real Windows work area (screen minus
taskbar), not a hardcoded height, so this behaves at 100%-150% DPI scaling.
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import settings as _settings
from hotkey import DEFAULT_HOTKEY, format_hotkey, is_valid_hotkey
from settings import parse_game_processes
from speakeasy_log import log_event
from status_dot import _work_area
from theme import ACCENT, BG, COLOR_ERROR, FONT_FAMILY, MUTED, SURFACE, TEXT
from transcription import VALID_MODELS
from version import __version__

GITHUB_URL = "https://github.com/awesomo913/speakeasy"

_MODEL_HINTS = {
    "tiny": "tiny · fastest",
    "base": "base · fast",
    "small": "small · recommended",
    "medium": "medium · more accurate",
    "large-v3": "large-v3 · most accurate, slowest",
}

# code -> display name, in the order shown in the dropdown
_LANGUAGES = [
    ("auto", "Auto-detect"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("ru", "Russian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
    ("hi", "Hindi"),
]
_LANG_BY_LABEL = {label: code for code, label in _LANGUAGES}
_LANG_BY_CODE = {code: label for code, label in _LANGUAGES}

_WIDTH = 460
_SIDE_PAD = 20
_MIN_WORK_MARGIN = 80  # keep this much of the work area clear above/below

# Single live window — reopening just raises the existing one.
_win: tk.Toplevel | None = None


# ── Hotkey recorder — pure mapping, kept at module level so it's unit-testable
# without a Tk root (see tests/test_settings_window.py). ─────────────────────

_MODIFIER_TOKENS = {
    "Control_L": "<ctrl>", "Control_R": "<ctrl>",
    "Alt_L": "<alt>", "Alt_R": "<alt>",
    "Shift_L": "<shift>", "Shift_R": "<shift>",
    "Super_L": "<cmd>", "Super_R": "<cmd>",
}
MODIFIER_TOKEN_SET = set(_MODIFIER_TOKENS.values())

# Tk keysym -> pynput Key name, for named (non-modifier, non-F-key) keys.
_NAMED_KEY_MAP = {
    "Return": "enter",
    "BackSpace": "backspace",
    "Tab": "tab",
    "Delete": "delete",
    "Insert": "insert",
    "Home": "home",
    "End": "end",
    "Prior": "page_up",
    "Next": "page_down",
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
    "Caps_Lock": "caps_lock",
    "Num_Lock": "num_lock",
    "Scroll_Lock": "scroll_lock",
    "Print": "print_screen",
    "Pause": "pause",
    "Menu": "menu",
}


def keysym_to_token(keysym: str) -> str | None:
    """Map a Tk <KeyPress> keysym to a pynput hotkey token, or None if unmappable.

    Modifiers -> "<ctrl>"/"<alt>"/"<shift>"/"<cmd>". Letters and digits -> the
    lowercase character (e.g. "d", "5"). F-keys -> "<f9>". Space -> "<space>".
    Other named keys (Tab, Return, arrows, ...) -> "<name>" via pynput's Key
    naming. "Escape" is intentionally NOT mapped here — the recorder treats it
    as "cancel", never as a bindable key.
    """
    if not keysym or keysym == "Escape":
        return None
    if keysym in _MODIFIER_TOKENS:
        return _MODIFIER_TOKENS[keysym]
    if keysym == "space":
        return "<space>"
    if len(keysym) == 1:
        return keysym.lower()
    lower = keysym.lower()
    if lower.startswith("f") and lower[1:].isdigit():
        return f"<{lower}>"
    if keysym in _NAMED_KEY_MAP:
        return f"<{_NAMED_KEY_MAP[keysym]}>"
    return None


def is_f_key_token(token: str) -> bool:
    """True for a token like "<f9>" (an F-key, the one modifier-free exception)."""
    return token.startswith("<f") and token.endswith(">") and token[2:-1].isdigit()


_MOD_PRIORITY = {"<ctrl>": 0, "<alt>": 1, "<shift>": 2, "<cmd>": 3}


def build_combo(mods: set, token: str) -> str:
    """Join held modifier tokens + the finishing key into a pynput hotkey string."""
    ordered_mods = sorted(mods, key=lambda t: (_MOD_PRIORITY.get(t, 9), t))
    return "+".join([*ordered_mods, token])


def validate_combo(mods: set, token: str) -> tuple[bool, str]:
    """Validate a candidate (mods, finishing-key) pair.

    Returns (ok, combo_or_error). A combo needs a modifier UNLESS the
    finishing key is an F-key.
    """
    if not mods and not is_f_key_token(token):
        return False, "Add a modifier (Ctrl / Alt / Shift / Win), or use an F key."
    combo = build_combo(mods, token)
    if not is_valid_hotkey(combo):
        return False, "That key can't be used for a shortcut."
    return True, combo


# ── Small building blocks ────────────────────────────────────────────────────

def _configure_styles(root: tk.Misc) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError as exc:
        log_event("warning", "ttk clam theme unavailable; using default", {"error": str(exc)})

    style.configure("SE.TCombobox",
                     fieldbackground=SURFACE, background=SURFACE, foreground=TEXT,
                     arrowcolor=TEXT, bordercolor=SURFACE, lightcolor=SURFACE,
                     darkcolor=SURFACE)
    style.map("SE.TCombobox",
              fieldbackground=[("readonly", SURFACE)],
              foreground=[("readonly", TEXT)],
              bordercolor=[("focus", ACCENT), ("!focus", SURFACE)],
              lightcolor=[("focus", ACCENT), ("!focus", SURFACE)],
              darkcolor=[("focus", ACCENT), ("!focus", SURFACE)])

    style.configure("SEPrimary.TButton", background=ACCENT, foreground="#0c0c14",
                     font=(FONT_FAMILY, 10, "bold"), borderwidth=0, padding=(16, 8))
    style.map("SEPrimary.TButton", background=[("active", "#28b0a3")])

    style.configure("SESecondary.TButton", background=SURFACE, foreground=TEXT,
                     font=(FONT_FAMILY, 10), borderwidth=0, padding=(16, 8))
    style.map("SESecondary.TButton", background=[("active", "#2a2a3d")])

    style.configure("SE.Vertical.TScrollbar", background=SURFACE, troughcolor=BG,
                     bordercolor=BG, arrowcolor=TEXT, relief="flat", gripcount=0)
    style.map("SE.Vertical.TScrollbar", background=[("active", "#2a2a3d")])


def _section(parent: tk.Widget, title: str) -> tk.Frame:
    """A titled section: small uppercase header + a frame for its contents."""
    wrap = tk.Frame(parent, bg=BG)
    wrap.pack(fill="x", padx=_SIDE_PAD, pady=(16, 0))
    header = tk.Label(
        wrap, text=title.upper(), font=(FONT_FAMILY, 9, "bold"),
        bg=BG, fg=MUTED, anchor="w",
    )
    header.pack(fill="x")
    body = tk.Frame(wrap, bg=BG)
    body.pack(fill="x", pady=(8, 0))
    return body


def _entry(parent: tk.Widget, **kw) -> tk.Entry:
    return tk.Entry(
        parent, bg=SURFACE, fg=TEXT, relief="flat",
        insertbackground=TEXT, font=(FONT_FAMILY, 10),
        highlightthickness=1, highlightbackground=SURFACE, highlightcolor=ACCENT,
        **kw,
    )


def _help_label(parent: tk.Widget, text: str, fg: str = MUTED) -> tk.Label:
    return tk.Label(
        parent, text=text, font=(FONT_FAMILY, 8), bg=BG, fg=fg,
        anchor="w", justify="left", wraplength=_WIDTH - _SIDE_PAD * 2 - 20,
    )


class ToggleSwitch(tk.Frame):
    """A small pill-shaped on/off switch bound to a tk.BooleanVar.

    Replaces the Win95-look ttk.Checkbutton box everywhere in this window.
    Click or Space (when focused) toggles; a teal focus ring shows keyboard
    focus so it stays accessible.
    """

    _W = 36
    _H = 20

    def __init__(
        self, parent: tk.Widget, variable: tk.BooleanVar, text: str = "",
        command=None, **kw,
    ):
        super().__init__(parent, bg=BG, **kw)
        self._var = variable
        self._command = command
        self._focused = False

        self._canvas = tk.Canvas(
            self, width=self._W, height=self._H, bg=BG,
            highlightthickness=0, cursor="hand2", takefocus=1,
        )
        self._canvas.pack(side="left")

        self._label: tk.Label | None = None
        if text:
            # wraplength keeps a long label from running past the window's
            # right edge instead of clipping — it wraps to a second line.
            self._label = tk.Label(
                self, text=text, font=(FONT_FAMILY, 10), bg=BG, fg=TEXT,
                anchor="w", justify="left", cursor="hand2",
                wraplength=_WIDTH - _SIDE_PAD * 2 - self._W - 8,
            )
            self._label.pack(side="left", padx=(8, 0), fill="x", expand=True)
            self._label.bind("<Button-1>", lambda _e: self._toggle())

        self._canvas.bind("<Button-1>", lambda _e: self._toggle())
        self._canvas.bind("<Key-space>", lambda _e: self._toggle())
        self._canvas.bind("<Return>", lambda _e: self._toggle())
        self._canvas.bind("<FocusIn>", self._on_focus_in)
        self._canvas.bind("<FocusOut>", self._on_focus_out)
        self._var.trace_add("write", lambda *_a: self._redraw())
        self._redraw()

    def _on_focus_in(self, _event) -> None:
        self._focused = True
        self._redraw()

    def _on_focus_out(self, _event) -> None:
        self._focused = False
        self._redraw()

    def _toggle(self) -> None:
        self._canvas.focus_set()
        self._var.set(not self._var.get())
        if self._command is not None:
            try:
                self._command()
            except Exception as exc:  # noqa: BLE001 — a toggle callback must not crash Save
                log_event("failure", "toggle switch callback failed", {"error": str(exc)})

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        on = bool(self._var.get())
        pill = ACCENT if on else "#3a3a4d"
        r = self._H // 2
        c.create_oval(0, 0, self._H, self._H, fill=pill, outline="")
        c.create_oval(self._W - self._H, 0, self._W, self._H, fill=pill, outline="")
        c.create_rectangle(r, 0, self._W - r, self._H, fill=pill, outline="")
        knob_x = self._W - r if on else r
        c.create_oval(knob_x - 8, 2, knob_x + 8, self._H - 2, fill="#f4f4fa", outline="")
        if self._focused:
            c.create_rectangle(1, 1, self._W - 1, self._H - 1, outline=ACCENT, width=2)


def _bool_row(parent: tk.Widget, text: str, variable: tk.BooleanVar, top_pad: int = 0):
    row = ToggleSwitch(parent, variable, text=text)
    row.pack(anchor="w", pady=(top_pad, 0))
    return row


# ── Main window ──────────────────────────────────────────────────────────────

def open_settings_window(root: tk.Tk, on_dot_toggle=None, on_settings_saved=None) -> None:
    """Open (or raise) the settings window. Must run on the main thread.

    on_dot_toggle: optional zero-arg callback fired when the status-dot
    checkbox flips, so the app applies visibility live.
    on_settings_saved: optional zero-arg callback fired after a successful
    Save, so the app can re-apply live-tunable settings (hotkey, triggers,
    game guard) without a restart.
    """
    global _win
    if _win is not None:
        try:
            if _win.winfo_exists():
                _win.deiconify()
                _win.lift()
                _win.focus_force()
                return
        except tk.TclError:
            pass
        _win = None

    _configure_styles(root)

    win = tk.Toplevel(root)
    _win = win
    win.title("SpeakEasy Settings")
    win.configure(bg=BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)

    saved = _settings.load()

    # ── Scroll area (Canvas + inner frame) — footer is added AFTER this and
    # packed with side="bottom" so it stays outside the scrollable region. ──
    scroll_wrap = tk.Frame(win, bg=BG)
    canvas = tk.Canvas(scroll_wrap, bg=BG, highlightthickness=0)
    vsb = ttk.Scrollbar(
        scroll_wrap, orient="vertical", command=canvas.yview, style="SE.Vertical.TScrollbar",
    )
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    body = tk.Frame(canvas, bg=BG)
    body_id = canvas.create_window((0, 0), window=body, anchor="nw")

    def _on_body_configure(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event) -> None:
        canvas.itemconfig(body_id, width=event.width)

    body.bind("<Configure>", _on_body_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(event) -> None:
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(_event=None) -> None:
        win.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_wheel(_event=None) -> None:
        win.unbind_all("<MouseWheel>")

    win.bind("<Enter>", _bind_wheel)
    win.bind("<Leave>", _unbind_wheel)

    # ── Header ───────────────────────────────────────────────────────
    header = tk.Frame(body, bg=BG)
    header.pack(fill="x", padx=_SIDE_PAD, pady=(20, 4))
    tk.Label(
        header, text="SpeakEasy", font=(FONT_FAMILY, 16, "bold"), bg=BG, fg=TEXT,
    ).pack(side="left")
    tk.Label(
        header, text="Settings", font=(FONT_FAMILY, 16), bg=BG, fg=MUTED,
    ).pack(side="left", padx=(8, 0))

    # ── Trigger ──────────────────────────────────────────────────────
    trigger = _section(body, "Trigger")

    mouse_var = tk.BooleanVar(value=bool(saved.get("mouse_button", True)))
    _bool_row(trigger, "Mouse side button (Back / XButton1)", mouse_var)

    hotkey_row = tk.Frame(trigger, bg=BG)
    hotkey_row.pack(fill="x", pady=(14, 0))
    tk.Label(hotkey_row, text="Keyboard hotkey:", font=(FONT_FAMILY, 9),
              bg=BG, fg=MUTED).pack(anchor="w")

    chip_row = tk.Frame(hotkey_row, bg=BG)
    chip_row.pack(fill="x", pady=(4, 0))

    hotkey_var = tk.StringVar(value=saved.get("hotkey", ""))  # real pynput string
    chip_var = tk.StringVar(value=format_hotkey(hotkey_var.get()))  # displayed text

    chip_frame = tk.Frame(
        chip_row, bg=SURFACE, highlightthickness=2,
        highlightbackground=SURFACE, highlightcolor=SURFACE,
    )
    chip_frame.pack(side="left", fill="x", expand=True)
    chip_label = tk.Label(
        chip_frame, textvariable=chip_var, font=(FONT_FAMILY, 10, "bold"),
        bg=SURFACE, fg=TEXT, anchor="w", padx=10, pady=6,
    )
    chip_label.pack(fill="x")

    hint_var = tk.StringVar(value="")
    _recording = {"active": False, "mods": set()}

    def _update_chip() -> None:
        chip_var.set(format_hotkey(hotkey_var.get()))

    def _set_recording_visual(active: bool) -> None:
        color = ACCENT if active else SURFACE
        chip_frame.config(highlightbackground=color, highlightcolor=color)

    def _finalize(token: str) -> None:
        ok, result = validate_combo(_recording["mods"], token)
        if not ok:
            hint_var.set(result)
            return
        hotkey_var.set(result)
        hint_var.set("")
        _stop_recording()

    def _start_recording() -> None:
        _recording["active"] = True
        _recording["mods"] = set()
        hint_var.set("")
        chip_var.set("Press your shortcut…")
        _set_recording_visual(True)
        change_btn.config(text="Cancel (Esc)")
        clear_btn.config(state="disabled")
        change_btn.focus_set()

    def _stop_recording() -> None:
        _recording["active"] = False
        _recording["mods"] = set()
        _set_recording_visual(False)
        change_btn.config(text="Change…")
        clear_btn.config(state="normal")
        _update_chip()

    def _on_key_press(event) -> str:
        if not _recording["active"]:
            return "break"
        if event.keysym == "Escape":
            hint_var.set("")
            _stop_recording()
            return "break"
        token = keysym_to_token(event.keysym)
        if token is None:
            return "break"
        if token in MODIFIER_TOKEN_SET:
            _recording["mods"].add(token)
            return "break"
        _finalize(token)
        return "break"

    def _on_key_release(event) -> None:
        if not _recording["active"]:
            return
        token = keysym_to_token(event.keysym)
        if token in MODIFIER_TOKEN_SET:
            _recording["mods"].discard(token)

    def _toggle_recording() -> None:
        if _recording["active"]:
            hint_var.set("")
            _stop_recording()
        else:
            _start_recording()

    def _clear_hotkey() -> None:
        if _recording["active"]:
            _stop_recording()
        hotkey_var.set("")
        hint_var.set("")
        _update_chip()

    change_btn = ttk.Button(
        chip_row, text="Change…", style="SESecondary.TButton", command=_toggle_recording,
    )
    change_btn.pack(side="left", padx=(10, 0))
    change_btn.bind("<KeyPress>", _on_key_press)
    change_btn.bind("<KeyRelease>", _on_key_release)

    clear_btn = ttk.Button(
        chip_row, text="Clear", style="SESecondary.TButton", command=_clear_hotkey,
    )
    clear_btn.pack(side="left", padx=(8, 0))

    tk.Label(
        hotkey_row, textvariable=hint_var, font=(FONT_FAMILY, 8), bg=BG, fg=COLOR_ERROR,
        anchor="w", wraplength=_WIDTH - _SIDE_PAD * 2 - 20,
    ).pack(anchor="w", pady=(6, 0))

    _help_label(
        trigger, f"Default: {format_hotkey(DEFAULT_HOTKEY)}",
    ).pack(anchor="w", pady=(6, 0))

    # ── Speech ───────────────────────────────────────────────────────
    speech = _section(body, "Speech")

    model_row = tk.Frame(speech, bg=BG)
    model_row.pack(fill="x")
    tk.Label(model_row, text="Model", font=(FONT_FAMILY, 9), bg=BG, fg=MUTED,
              width=10, anchor="w").pack(side="left")
    model_var = tk.StringVar(
        value=_MODEL_HINTS.get(saved.get("model", "small"), _MODEL_HINTS["small"])
    )
    model_combo = ttk.Combobox(
        model_row, textvariable=model_var, state="readonly", style="SE.TCombobox",
        values=[_MODEL_HINTS[m] for m in VALID_MODELS], width=28,
    )
    model_combo.pack(side="left", fill="x", expand=True)
    _help_label(speech, "Changing the model takes effect on next launch.").pack(
        anchor="w", pady=(4, 8))

    lang_row = tk.Frame(speech, bg=BG)
    lang_row.pack(fill="x")
    tk.Label(lang_row, text="Language", font=(FONT_FAMILY, 9), bg=BG, fg=MUTED,
              width=10, anchor="w").pack(side="left")
    lang_var = tk.StringVar(value=_LANG_BY_CODE.get(saved.get("language", "auto"), "Auto-detect"))
    lang_combo = ttk.Combobox(
        lang_row, textvariable=lang_var, state="readonly", style="SE.TCombobox",
        values=[label for _code, label in _LANGUAGES], width=28,
    )
    lang_combo.pack(side="left", fill="x", expand=True)

    # ── AI polish ────────────────────────────────────────────────────
    polish = _section(body, "AI polish")

    llm_var = tk.BooleanVar(value=bool(saved.get("llm_cleanup", False)))
    _bool_row(polish, "Polish transcript with AI before pasting", llm_var)

    key_row = tk.Frame(polish, bg=BG)
    key_row.pack(fill="x", pady=(14, 0))
    tk.Label(key_row, text="OpenRouter API key", font=(FONT_FAMILY, 9),
              bg=BG, fg=MUTED, anchor="w").pack(anchor="w")
    key_entry_row = tk.Frame(key_row, bg=BG)
    key_entry_row.pack(fill="x", pady=(4, 0))
    key_entry = _entry(key_entry_row, show="•", width=32)
    key_entry.insert(0, saved.get("llm_api_key", ""))
    key_entry.pack(side="left", fill="x", expand=True, ipady=4)

    def _toggle_key_visibility() -> None:
        currently_masked = key_entry.cget("show") != ""
        key_entry.config(show="" if currently_masked else "•")
        show_lbl.config(text="Hide" if currently_masked else "Show")

    show_lbl = tk.Label(
        key_entry_row, text="Show", font=(FONT_FAMILY, 9, "underline"),
        bg=BG, fg=ACCENT, cursor="hand2",
    )
    show_lbl.pack(side="left", padx=(8, 0))
    show_lbl.bind("<Button-1>", lambda _e: _toggle_key_visibility())

    model_entry_row = tk.Frame(polish, bg=BG)
    model_entry_row.pack(fill="x", pady=(8, 0))
    tk.Label(model_entry_row, text="Model", font=(FONT_FAMILY, 9), bg=BG, fg=MUTED,
              width=10, anchor="w").pack(side="left")
    llm_model_entry = _entry(model_entry_row)
    llm_model_entry.insert(0, saved.get("llm_model", "openai/gpt-4o-mini"))
    llm_model_entry.pack(side="left", fill="x", expand=True, ipady=4)

    _help_label(
        polish, "Optional. Sends only the transcribed text to OpenRouter.",
    ).pack(anchor="w", pady=(8, 0))

    # ── General ──────────────────────────────────────────────────────
    general = _section(body, "General")

    autostart_var = tk.BooleanVar(value=_settings.is_autostart_enabled())
    _bool_row(general, "Start SpeakEasy when Windows starts", autostart_var)

    dot_var = tk.BooleanVar(value=bool(saved.get("show_dot", True)))
    _bool_row(general, "Show status dot", dot_var, top_pad=10)

    guard_var = tk.BooleanVar(value=bool(saved.get("game_guard", True)))
    _bool_row(general, "Quit when a listed game starts", guard_var, top_pad=10)

    procs_row = tk.Frame(general, bg=BG)
    procs_row.pack(fill="x", pady=(12, 0))
    tk.Label(procs_row, text="Guarded processes (comma-separated):",
              font=(FONT_FAMILY, 9), bg=BG, fg=MUTED, anchor="w").pack(anchor="w")
    procs_entry = _entry(procs_row)
    procs_entry.insert(0, ", ".join(saved.get("game_processes", [])))
    procs_entry.pack(fill="x", pady=(4, 0), ipady=4)

    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(
        body, textvariable=status_var, font=(FONT_FAMILY, 9), bg=BG, fg=MUTED,
        anchor="w", wraplength=_WIDTH - _SIDE_PAD * 2 - 20,
    )
    status_lbl.pack(fill="x", padx=_SIDE_PAD, pady=(14, 0))

    footer_links = tk.Frame(body, bg=BG)
    footer_links.pack(fill="x", padx=_SIDE_PAD, pady=(16, 20))
    tk.Label(footer_links, text=f"v{__version__}", font=(FONT_FAMILY, 8),
              bg=BG, fg=MUTED).pack(anchor="w")
    gh_link = tk.Label(
        footer_links, text="GitHub", font=(FONT_FAMILY, 8, "underline"),
        bg=BG, fg=ACCENT, cursor="hand2",
    )
    gh_link.pack(anchor="w")
    gh_link.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL))

    scroll_wrap.pack(fill="both", expand=True)

    # ── Footer (Save/Cancel) — packed OUTSIDE the scroll area ───────────
    footer = tk.Frame(win, bg=SURFACE)
    footer.pack(fill="x", side="bottom")
    btn_row = tk.Frame(footer, bg=SURFACE)
    btn_row.pack(fill="x", padx=_SIDE_PAD, pady=12)

    def _gather_settings() -> dict:
        data = _settings.load()
        data["mouse_button"] = bool(mouse_var.get())
        hotkey = hotkey_var.get().strip()
        data["hotkey"] = hotkey if is_valid_hotkey(hotkey) else ""
        data["model"] = next(
            (m for m in VALID_MODELS if _MODEL_HINTS[m] == model_var.get()), "small",
        )
        data["language"] = _LANG_BY_LABEL.get(lang_var.get(), "auto")
        data["llm_cleanup"] = bool(llm_var.get())
        data["llm_api_key"] = key_entry.get().strip()
        data["llm_model"] = llm_model_entry.get().strip() or "openai/gpt-4o-mini"
        data["show_dot"] = bool(dot_var.get())
        data["game_guard"] = bool(guard_var.get())
        data["game_processes"] = parse_game_processes(procs_entry.get())
        return data

    def _on_save() -> None:
        data = _gather_settings()
        if not _settings.save(data):
            status_var.set("Couldn't save settings — see logs.")
            log_event("failure", "settings save failed from settings window")
            return

        # Autostart is a side effect (creates/removes a Startup shortcut), not
        # just a JSON field — apply it separately and report failure honestly.
        want_autostart = bool(autostart_var.get())
        if want_autostart != _settings.is_autostart_enabled():
            if not _settings.set_autostart(want_autostart):
                autostart_var.set(_settings.is_autostart_enabled())
                messagebox.showerror(
                    "SpeakEasy", "Couldn't change autostart — see logs.", parent=win,
                )
                return

        log_event("decision", "settings saved from settings window", {})
        if on_dot_toggle is not None:
            try:
                on_dot_toggle()
            except Exception as exc:  # noqa: BLE001 — a UI callback must not crash Save
                log_event("failure", "dot toggle callback failed", {"error": str(exc)})
        if on_settings_saved is not None:
            try:
                on_settings_saved()
            except Exception as exc:  # noqa: BLE001
                log_event("failure", "settings saved callback failed", {"error": str(exc)})
        _close()

    def _close() -> None:
        global _win
        _unbind_wheel()
        _win = None
        win.destroy()

    ttk.Button(
        btn_row, text="Save", style="SEPrimary.TButton", command=_on_save,
    ).pack(side="right")
    ttk.Button(
        btn_row, text="Cancel", style="SESecondary.TButton", command=_close,
    ).pack(side="right", padx=(0, 8))

    win.protocol("WM_DELETE_WINDOW", _close)

    # ── Size: min(natural content height, work area height - margin) ───────
    win.update_idletasks()
    natural_h = body.winfo_reqheight() + footer.winfo_reqheight() + 4
    left, top, right, bottom = _work_area()
    work_h = max(1, bottom - top)
    work_w = max(1, right - left)
    max_h = max(240, work_h - _MIN_WORK_MARGIN)
    final_h = min(natural_h, max_h)
    final_w = min(_WIDTH, work_w)

    if final_h < natural_h:
        # Content is taller than what fits — shrink the canvas so the
        # scrollbar takes over rather than the footer getting pushed off.
        canvas_h = max(120, final_h - footer.winfo_reqheight())
        canvas.configure(height=canvas_h)

    x = left + max(0, (work_w - final_w) // 2)
    y = top + max(0, (work_h - final_h) // 2)
    win.geometry(f"{final_w}x{final_h}+{x}+{y}")
    log_event("state", "settings window opened")
