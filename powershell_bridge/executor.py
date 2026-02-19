"""
PowerShell Bridge — Execution engine.
Runs run.bat, parses report.json, returns structured results.
Windows-first design: .bat -> run.ps1 filter layer.
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Tuple


def tail_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    txt = path.read_text(encoding="utf-8", errors="replace")
    return txt[-max_chars:]


def run_session(run_dir: Path, timeout_s: int) -> Tuple[int, dict, str]:
    """
    Execute run.bat inside run_dir.
    Returns (returncode, report_dict, log_tail).
    Windows-only: requires cmd.exe.
    """
    bat = run_dir / "run.bat"
    report_path = run_dir / "report.json"
    log_path = run_dir / "run.log"

    if os.name != "nt":
        return 501, {"error": "PowerShell .bat bridge requires Windows cmd.exe/powershell.exe."}, ""

    try:
        completed = subprocess.run(
            ["cmd.exe", "/c", str(bat)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s
        )
        report = {}
        if report_path.exists():
            raw = report_path.read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM
            report = json.loads(raw)
        return completed.returncode, report, tail_text(log_path)
    except subprocess.TimeoutExpired:
        return -1, {"error": "Execution timeout"}, tail_text(log_path)
    except Exception as e:
        return -2, {"error": str(e)}, tail_text(log_path)
