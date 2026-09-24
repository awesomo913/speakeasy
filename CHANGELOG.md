# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-24

### Added

- Press-to-talk dictation anywhere on Windows: press a trigger, talk, press again (or stay silent for 10 seconds) to paste the transcript at your cursor.
- Triggers: mouse "Back" side button (can be disabled) and a rebindable keyboard hotkey, default `Ctrl+Alt+D`.
- 100% local speech-to-text using faster-whisper (OpenAI Whisper), running on CPU with no account, subscription, or cloud dependency.
- Selectable Whisper model: tiny, base, small (default), medium, large-v3.
- Auto-detect or pick a specific dictation language.
- Long dictation support: up to 10 minutes per recording, auto-stop after 10 seconds of silence.
- Clipboard-based paste that restores the user's previous clipboard contents afterward.
- Optional "AI polish" pass (off by default) that sends only the transcribed text to OpenRouter, using the user's own API key, to remove filler words and fix punctuation while preserving code identifiers, camelCase, and file paths. Falls back to the raw transcript on any failure.
- Floating pill overlay near the cursor showing recording / transcribing / pasted state.
- Draggable status dot near the taskbar (teal = ready, red = recording, blue = transcribing, grey = paused).
- System tray menu: pause/resume, settings, open log folder, quit.
- Modern dark settings window.
- Start-at-login option.
- Single-instance guard.
- Game guard: auto-quits when a listed game process launches (default: Fortnite) to avoid mouse-hook interference; list is editable and the feature can be disabled.
- Settings persisted at `%APPDATA%\SpeakEasy\settings.json`; logs at `%LOCALAPPDATA%\SpeakEasy\logs`.
- Portable single-file `SpeakEasy.exe` distributed via GitHub Releases, built by GitHub Actions on tag with an attached `SHA256SUMS.txt`.
