# Contributing to SpeakEasy

Thanks for considering a contribution. SpeakEasy is a small, free, open-source Windows dictation app — issues and PRs of any size are welcome.

## Dev setup

Requires Python 3.11 on Windows.

```bash
git clone https://github.com/awesomo913/speakeasy.git
cd speakeasy
pip install -r requirements.txt
# or: uv pip install -r requirements.txt
python main.py
```

For building the exe and running the full check suite, also install the dev dependencies:

```bash
pip install -r requirements-dev.txt
```

## Running tests and lint

```bash
pytest
ruff check .
```

Please run both before opening a PR.

## Code style

- Small, focused modules over large ones.
- No silent `except:` blocks — catch specific exceptions, log or surface them, never swallow.
- Anything that touches the GUI (tkinter) must run on the main thread; background threads should hand results back via a queue, not touch widgets directly.
- Keep functions short and prefer early returns over deep nesting.
- Match the existing logging style (`log_event(...)`) rather than adding `print()` calls in library code.

## Good first issues

Looking for a place to start? These roadmap items are scoped well for a first PR:

- Push-to-talk hold mode (hold the trigger instead of toggling)
- Custom vocabulary / word-list support
- Editable "voice snippets" (short phrases mapped to a spoken trigger word)
- winget or scoop packaging manifest

Check open issues first in case someone's already working on one — comment to claim it.

## Pull request checklist

- [ ] `pytest` passes
- [ ] `ruff check .` passes with no new warnings
- [ ] No new silent exception handling
- [ ] GUI changes only touch tkinter from the main thread
- [ ] Updated `CHANGELOG.md` under `[Unreleased]` if the change is user-facing
- [ ] Description explains *why*, not just *what*
