"""Hotkey parsing/matching tests — drive the listener press path directly (no hook, no window)."""
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

import hotkey
from hotkey import DEFAULT_HOTKEY, HotkeyListener, format_hotkey, is_valid_hotkey


def test_empty_hotkey_is_valid_disabled():
    assert is_valid_hotkey("") is True
    assert is_valid_hotkey("   ") is True


def test_well_formed_hotkeys_are_valid():
    assert is_valid_hotkey(DEFAULT_HOTKEY) is True
    assert is_valid_hotkey("<ctrl>+<alt>+<space>") is True
    assert is_valid_hotkey("<ctrl>+<shift>+m") is True


def test_garbage_hotkey_is_invalid():
    assert is_valid_hotkey("not a hotkey at all!!") is False


def test_format_hotkey():
    assert format_hotkey("<ctrl>+<alt>+d") == "Ctrl + Alt + D"
    assert format_hotkey("<ctrl>+<shift>+<space>") == "Ctrl + Shift + Space"
    assert format_hotkey("<cmd>+<f9>") == "Win + F9"
    assert format_hotkey("") == "Off"


def _fires(combo: str, events) -> bool:
    """Feed press/release events the way the Windows listener would deliver them."""
    hits = []
    lst = HotkeyListener(on_toggle=lambda x, y: hits.append((x, y)))
    lst._hotkey = keyboard.HotKey(hotkey.parse_hotkey(combo), lst._fire)
    lst._listener = keyboard.Listener()  # not started; only used for canonical()
    for k in events:
        lst._on_press(k, False)
    for k in reversed(events):
        lst._on_release(k, False)
    return bool(hits)


def test_letter_combo_matches_every_windows_event_shape():
    # While Ctrl is held, Windows may report "d" as vk-only, as a control char,
    # or as the plain char — all must trigger.
    for ev in (KeyCode.from_vk(0x44), KeyCode(vk=0x44, char="\x04"), KeyCode(vk=0x44, char="d")):
        assert _fires("<ctrl>+<alt>+d", [Key.ctrl_l, Key.alt_l, ev]), ev


def test_named_key_combo_and_right_modifiers():
    assert _fires("<ctrl>+<alt>+<space>", [Key.ctrl_r, Key.alt_l, Key.space])


def test_injected_events_are_accepted():
    lst_hits = []
    lst = HotkeyListener(on_toggle=lambda x, y: lst_hits.append(1))
    lst._hotkey = keyboard.HotKey(hotkey.parse_hotkey("<ctrl>+<alt>+d"), lst._fire)
    lst._listener = keyboard.Listener()
    for k in (Key.ctrl_l, Key.alt_l, KeyCode.from_vk(0x44)):
        lst._on_press(k, True)
    assert lst_hits


def test_wrong_letter_does_not_fire():
    assert not _fires("<ctrl>+<alt>+d", [Key.ctrl_l, Key.alt_l, KeyCode.from_vk(0x45)])
