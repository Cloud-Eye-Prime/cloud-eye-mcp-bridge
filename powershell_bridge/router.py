"""
PowerShell Bridge — FastAPI router.
Mount with:
    from powershell_bridge.router import router as ps_router
    app.include_router(ps_router, prefix="/powershell")

Endpoints:
    GET  /powershell/health
    POST /powershell/execute
    GET  /powershell/runs/{session_id}
    GET  /powershell/sessions
    POST /powershell/replay/{session_id}
"""
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .models import ExecuteRequest, ExecuteResult
from .session_builder import (
    new_session_id, ensure_run_dir,
    write_commands_json, write_ps1, write_bat
)
from .executor import run_session, tail_text

router = APIRouter()

API_TOKEN = os.environ.get("CLOUD_EYE_API_TOKEN", "wuji-neigong-2026")
RUNS_DIR = Path(os.environ.get("POWERSHELL_BRIDGE_RUNS_DIR", "ps_runs")).resolve()
POWERSHELL_EXE = os.environ.get("POWERSHELL_EXE", "powershell.exe")


def _auth(authorization: Optional[str]):
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health")
def ps_health():
    return {
        "status": "ready",
        "element": "fire",
        "runs_dir": str(RUNS_DIR),
        "powershell_exe": POWERSHELL_EXE,
        "platform": os.name
    }


@router.post("/execute", response_model=ExecuteResult)
def ps_execute(req: ExecuteRequest, authorization: Optional[str] = Header(None)):
    """
    Execute PowerShell commands through the defensive .bat filter layer.
    Every command becomes a replayable session with structured JSON logs.
    """
    _auth(authorization)
    if not req.commands:
        raise HTTPException(status_code=400, detail="No commands provided")
    session_id = req.session_id or new_session_id()
    run_dir = ensure_run_dir(RUNS_DIR, session_id)

    payload = {
        "session_id": session_id,
        "commands": [c.model_dump() for c in req.commands]
    }
    write_commands_json(run_dir, payload)
    write_ps1(run_dir)
    write_bat(
        run_dir,
        session_id=session_id,
        error_strategy=req.error_strategy,
        powershell_exe=POWERSHELL_EXE
    )

    timeout_s = max(c.timeout_s for c in req.commands) + 60
    rc, report, log_tail = run_session(run_dir, timeout_s=timeout_s)
    ok = rc == 0 and report.get("status") == "success"

    return ExecuteResult(
        session_id=session_id,
        ok=ok,
        returncode=rc,
        run_dir=str(run_dir),
        report=report,
        log_tail=log_tail
    )


@router.get("/runs/{session_id}")
def get_run(session_id: str, authorization: Optional[str] = Header(None)):
    """Retrieve structured report + log for a completed session."""
    _auth(authorization)
    run_dir = (RUNS_DIR / session_id).resolve()
    report_path = run_dir / "report.json"
    log_path = run_dir / "run.log"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "session_id": session_id,
        "report": json.loads(report_path.read_text(encoding="utf-8-sig")),
        "log": log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    }


@router.get("/sessions")
def list_sessions(authorization: Optional[str] = Header(None)):
    """List all recorded PowerShell sessions."""
    _auth(authorization)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for report_file in RUNS_DIR.glob("*/report.json"):
        try:
            data = json.loads(report_file.read_text(encoding="utf-8-sig"))
            sessions.append({
                "session_id": report_file.parent.name,
                "status": data.get("status", "unknown"),
                "started_at": data.get("started_at"),
                "failed": data.get("failed", 0)
            })
        except Exception:
            continue
    sessions.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    return {"count": len(sessions), "sessions": sessions}


@router.post("/replay/{session_id}")
def replay_session(session_id: str, authorization: Optional[str] = Header(None)):
    """Re-execute a previous session's .bat file for debugging / self-healing."""
    _auth(authorization)
    run_dir = (RUNS_DIR / session_id).resolve()
    bat = run_dir / "run.bat"
    if not bat.exists():
        raise HTTPException(status_code=404, detail="Session .bat not found")
    rc, report, log_tail = run_session(run_dir, timeout_s=300)
    return {
        "replayed": True,
        "session_id": session_id,
        "returncode": rc,
        "report": report,
        "log_tail": log_tail
    }
