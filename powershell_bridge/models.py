"""
PowerShell Bridge — Pydantic models.
"""
from pydantic import BaseModel
from typing import Optional, List


class PowerShellCommand(BaseModel):
    command: str
    args: List[str] = []
    working_dir: Optional[str] = None
    timeout_s: int = 60


class ExecuteRequest(BaseModel):
    commands: List[PowerShellCommand]
    session_id: Optional[str] = None
    error_strategy: str = "continue"  # continue | halt | retry


class ExecuteResult(BaseModel):
    session_id: str
    ok: bool
    returncode: int
    run_dir: str
    report: dict
    log_tail: str
