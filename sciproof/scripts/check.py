"""Portable Python validation entry point, independent of venv location."""
import subprocess
import sys
from pathlib import Path
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.call([sys.executable,'-m','pytest','tests','-q'],cwd=root))
