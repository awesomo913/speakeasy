"""Visual demo — cycles through all SpeakEasy overlay states so you can see them.

Run from the project root:  .venv-build\\Scripts\\python.exe scripts\\demo_overlay.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from overlay import Overlay  # noqa: E402

overlay = Overlay()

print("Showing RECORDING state (pulsing red dot) for 3 seconds...")
overlay.state_recording(600, 400)
time.sleep(3)

print("Showing TRANSCRIBING state (spinning blue dot) for 3 seconds...")
overlay.state_transcribing(600, 400)
time.sleep(3)

print("Showing PASTING state (checkmark + preview) for 3 seconds...")
overlay.state_pasting("Hello world this is SpeakEasy", 600, 400)
time.sleep(3)

print("Showing ERROR state for 2 seconds...")
overlay.state_error("No speech detected — try again", 600, 400)
time.sleep(2)

print("Demo complete! Overlay will auto-fade and hide.")
time.sleep(2)
overlay.destroy()
print("Done.")
