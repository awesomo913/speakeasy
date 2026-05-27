"""Visual demo — cycles through all SpeakEasy overlay states so you can see them."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from overlay import Overlay

overlay = Overlay()

print("Showing RECORDING state (red pulsing circle) for 3 seconds...")
overlay.state_recording(600, 400)
time.sleep(3)

print("Showing TRANSCRIBING state (blue circle) for 3 seconds...")
overlay.state_transcribing(600, 400)
time.sleep(3)

print("Showing PASTING state (green checkmark + preview) for 3 seconds...")
overlay.state_pasting("Hello world this is SpeakEasy", 600, 400)
time.sleep(3)

print("Showing ERROR state for 2 seconds...")
overlay.state_error("No speech detected — try again", 600, 400)
time.sleep(2)

print("Demo complete! Overlay will auto-fade and hide.")
time.sleep(2)
overlay.destroy()
print("Done.")
