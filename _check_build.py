"""Gate proof that _build_exe.py's llm_cleanup hidden-import took effect."""
import pathlib

here = pathlib.Path(__file__).parent
src = (here / "_build_exe.py").read_text(encoding="utf-8")
assert "--hidden-import=llm_cleanup" in src, "import line missing from _build_exe.py"
print("_build_exe.py declares --hidden-import=llm_cleanup")

toc = (here / "build" / "SpeakEasy" / "PYZ-00.toc").read_text(
    encoding="utf-8", errors="replace")
assert "llm_cleanup" in toc, "llm_cleanup not bundled in dist exe"
print("llm_cleanup bundled in dist/SpeakEasy.exe")

size_mb = (here / "dist" / "SpeakEasy.exe").stat().st_size / (1024 * 1024)
assert size_mb < 150, f"exe bloated: {size_mb:.1f} MB (torch leak?)"
print(f"dist exe size OK: {size_mb:.1f} MB (torch-free clean venv)")

print("BUILD PROOF OK")
