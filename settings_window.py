"""Small tkinter settings window for SpeakEasy.

Opened from the tray's "Settings" item. tkinter is main-thread-only, so this is
always invoked on the app's main loop (the tray callback enqueues a command;
main.py calls ``open_settings_window`` while pumping the Tk root) — never
directly from the pystray thread.

Built as a Toplevel on the app's existing root (Overlay owns the single tk.Tk),
so we don't create a second Tk instance.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

import settings as _settings

try:
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


# Palette matches the overlay so the app feels consistent.
_BG = "#1a1a2e"
_FG = "#e0e0e0"
_MUTED = "#8a8a9a"
_ACCENT = "#2a9d8f"
_RED = "#e63946"

# Single live window — reopening just raises the existing one.
_win: tk.Toplevel | None = None


def open_settings_window(root: tk.Tk, on_dot_toggle=None) -> None:
    """Open (or raise) the settings window. Must run on the main thread.

    on_dot_toggle: optional zero-arg callback fired when the status-dot
    checkbox flips, so the app applies visibility live (main.py passes one
    that enqueues a refresh_dot command).
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

    win = tk.Toplevel(root)
    _win = win
    win.title("SpeakEasy Settings")
    win.configure(bg=_BG)
    win.resizable(False, False)
    win.geometry("360x480")
    win.attributes("-topmost", True)

    # Header: app name + mic glyph.
    header = tk.Label(
        win, text="\U0001F399  SpeakEasy",
        font=tkfont.Font(size=15, weight="bold"),
        bg=_BG, fg=_RED,
    )
    header.pack(anchor="w", padx=18, pady=(16, 12))

    # Autostart checkbox — ground truth from the Startup shortcut itself.
    autostart_var = tk.BooleanVar(value=_settings.is_autostart_enabled())
    status_var = tk.StringVar()

    def _refresh_status() -> None:
        status_var.set(
            "Autostart: ON — launches at login"
            if autostart_var.get() else
            "Autostart: off"
        )

    def _on_toggle() -> None:
        want = autostart_var.get()
        ok = _settings.set_autostart(want)
        if not ok:
            # Revert the checkbox to reality so the UI never lies.
            autostart_var.set(_settings.is_autostart_enabled())
            status_var.set("Couldn't change autostart — see logs")
        else:
            _refresh_status()

    chk = tk.Checkbutton(
        win,
        text="Start SpeakEasy when Windows starts",
        variable=autostart_var,
        command=_on_toggle,
        bg=_BG, fg=_FG,
        selectcolor=_BG,
        activebackground=_BG, activeforeground=_FG,
        font=tkfont.Font(size=10),
        anchor="w",
    )
    chk.pack(anchor="w", padx=18)

    status = tk.Label(
        win, textvariable=status_var,
        font=tkfont.Font(size=9),
        bg=_BG, fg=_MUTED, anchor="w",
    )
    status.pack(anchor="w", padx=40, pady=(2, 0))
    _refresh_status()

    # ── AI polish (LLM cleanup) ──────────────────────────────────────
    sep1 = tk.Frame(win, height=1, bg=_MUTED)
    sep1.pack(fill="x", padx=18, pady=(12, 6))

    saved = _settings.load()
    llm_var = tk.BooleanVar(value=bool(saved.get("llm_cleanup", False)))
    llm_status_var = tk.StringVar()

    def _save_llm_fields() -> None:
        data = _settings.load()
        data["llm_cleanup"] = bool(llm_var.get())
        data["llm_api_key"] = key_entry.get().strip()
        data["llm_model"] = model_entry.get().strip() or "openai/gpt-4o-mini"
        # settings.save() reports failure via False (not an exception) — turn
        # it into one so callers can't mistake a failed save for success.
        if not _settings.save(data):
            raise OSError("settings.save() reported failure")

    def _llm_refresh() -> None:
        if llm_var.get():
            key_ok = bool(key_entry.get().strip())
            llm_status_var.set(
                "AI polish: ON — transcript cleaned before paste"
                if key_ok else
                "AI polish: ON but no API key — pasting raw until key saved"
            )
        else:
            llm_status_var.set("AI polish: off — raw transcript pasted")

    def _autosave() -> None:
        try:
            _save_llm_fields()
        except Exception as exc:
            log_event("failure", "settings autosave failed", {"error": str(exc)})
            llm_status_var.set("Couldn't save settings — see logs")
            return
        _llm_refresh()

    llm_chk = tk.Checkbutton(
        win,
        text="Polish with AI (LLM cleanup)",
        variable=llm_var,
        command=_autosave,
        bg=_BG, fg=_FG,
        selectcolor=_BG,
        activebackground=_BG, activeforeground=_FG,
        font=tkfont.Font(size=10),
        anchor="w",
    )
    llm_chk.pack(anchor="w", padx=18)

    llm_status = tk.Label(
        win, textvariable=llm_status_var,
        font=tkfont.Font(size=9),
        bg=_BG, fg=_MUTED, anchor="w",
    )
    llm_status.pack(anchor="w", padx=40, pady=(2, 6))

    key_lbl = tk.Label(
        win, text="OpenRouter API key:",
        font=tkfont.Font(size=9),
        bg=_BG, fg=_MUTED, anchor="w",
    )
    key_lbl.pack(anchor="w", padx=18)
    key_entry = tk.Entry(
        win, show="•", width=40,
        bg="#26263a", fg=_FG, relief="flat", insertbackground=_FG,
        font=tkfont.Font(size=10),
    )
    key_entry.insert(0, saved.get("llm_api_key", ""))
    key_entry.pack(anchor="w", padx=18, pady=(2, 6))
    key_entry.bind("<FocusOut>", lambda _e: _autosave())
    key_entry.bind("<Return>", lambda _e: _autosave())

    model_lbl = tk.Label(
        win, text="Model:",
        font=tkfont.Font(size=9),
        bg=_BG, fg=_MUTED, anchor="w",
    )
    model_lbl.pack(anchor="w", padx=18)
    model_entry = tk.Entry(
        win, width=40,
        bg="#26263a", fg=_FG, relief="flat", insertbackground=_FG,
        font=tkfont.Font(size=10),
    )
    model_entry.insert(0, saved.get("llm_model", "openai/gpt-4o-mini"))
    model_entry.pack(anchor="w", padx=18, pady=(2, 0))
    model_entry.bind("<FocusOut>", lambda _e: _autosave())
    model_entry.bind("<Return>", lambda _e: _autosave())
    _llm_refresh()

    # ── Status dot visibility ─────────────────────────────────────────
    sep2 = tk.Frame(win, height=1, bg=_MUTED)
    sep2.pack(fill="x", padx=18, pady=(12, 6))

    dot_var = tk.BooleanVar(value=bool(saved.get("show_dot", True)))

    def _dot_toggle() -> None:
        data = _settings.load()
        data["show_dot"] = bool(dot_var.get())
        # Same honesty rule as the LLM fields: a failed save must not
        # pretend it persisted (skeptic 2026-09-13).
        if not _settings.save(data):
            log_event("failure", "status dot save failed")
            dot_var.set(not dot_var.get())
            try:
                from tkinter import messagebox
                messagebox.showerror(
                    "SpeakEasy",
                    "Couldn't save settings — dot visibility was NOT saved.",
                    parent=win,
                )
            except Exception:
                pass
            return
        log_event("decision", "status dot toggled", {"visible": bool(dot_var.get())})
        if on_dot_toggle is not None:
            try:
                on_dot_toggle()
            except Exception as exc:
                log_event("failure", "dot toggle callback failed", {"error": str(exc)})

    dot_chk = tk.Checkbutton(
        win,
        text="Show status dot",
        variable=dot_var,
        command=_dot_toggle,
        bg=_BG, fg=_FG,
        selectcolor=_BG,
        activebackground=_BG, activeforeground=_FG,
        font=tkfont.Font(size=10),
        anchor="w",
    )
    dot_chk.pack(anchor="w", padx=18, pady=(0, 4))

    # Close button, bottom-right. Saves key/model fields first so typing a
    # key and clicking Close directly never loses it. If the save FAILS the
    # window stays open with an error (skeptic 2026-09-13: silently closing
    # would make the user believe the key was saved when it wasn't).
    def _on_close_btn() -> None:
        global _win
        try:
            _save_llm_fields()
        except Exception as exc:
            log_event("failure", "settings save on close failed", {"error": str(exc)})
            try:
                from tkinter import messagebox
                messagebox.showerror(
                    "SpeakEasy",
                    "Couldn't save settings — your API key was NOT saved.\n"
                    f"Error: {exc}",
                    parent=win,
                )
            except Exception:
                pass
            return
        _win = None
        win.destroy()

    btn = tk.Button(
        win, text="Close", command=_on_close_btn,
        bg=_ACCENT, fg="#ffffff", relief="flat",
        activebackground="#23867a", activeforeground="#ffffff",
        font=tkfont.Font(size=10, weight="bold"),
        width=10, cursor="hand2",
    )
    btn.pack(side="bottom", anchor="e", padx=18, pady=16)

    # X button saves exactly like Close (skeptic 2026-09-13: destroying
    # directly here used to drop an unsaved API key in silence).
    win.protocol("WM_DELETE_WINDOW", _on_close_btn)
    log_event("state", "settings window opened")
