"""Build the current standalone macOS App; see packaging/build_macos.py."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1]/"packaging/build_macos.py"),run_name="__main__")
