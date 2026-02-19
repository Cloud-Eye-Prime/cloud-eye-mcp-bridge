"""
Librarian 2.0 — Reality Scanner
Probes the actual state of the system: git, HTTP, filesystem.
Returns ground truth that the Illusion Detector compares against recorded beliefs.

Wu Xing: Metal — precision, harvest, what is actually present.
"""
import subprocess
import asyncio
import sqlite3
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    import urllib.request

from .config import REPOS, SERVICES, HTTP_TIMEOUT, LIBRARIAN_DB, SAPPHIRE_DB


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class GitState:
    repo_name: str
    repo_path: Path
    available: bool
    head_commit: Optional[str] = None
    branch: Optional[str] = None
    untracked: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    staged: List[str] = field(default_factory=list)
    ahead_behind: Optional[str] = None
    error: Optional[str] = None

@dataclass
class ServiceState:
    name: str
    url: str
    reachable: bool
    status_code: Optional[int] = None
    response_ms: Optional[float] = None
    version: Optional[str] = None
    health_detail: Optional[dict] = None
    error: Optional[str] = None

@dataclass
class LibrarianState:
    db_path: Path
    readable: bool
    total_guidance: int = 0
    current_focus_count: int = 0
    essence_count: int = 0
    recent_handoff: Optional[str] = None
    embedding_coverage_pct: float = 0.0
    error: Optional[str] = None

@dataclass
class SapphireState:
    db_path: Path
    readable: bool
    routing_observations: int = 0
    detected_patterns: int = 0
    unapplied_patterns: int = 0
    recent_observation: Optional[str] = None
    error: Optional[str] = None

@dataclass
class RealitySnapshot:
    scanned_at: str
    scan_duration_ms: float
    git: Dict[str, GitState]
    services: Dict[str, ServiceState]
    librarian: LibrarianState
    sapphire: SapphireState
    filesystem: Dict[str, bool]  # path → exists


# ─── Git Probing ──────────────────────────────────────────────────────────────

def _git(args: List[str], cwd: Path) -> Optional[str]:
    """Run a git command, return stdout or None on error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None

def scan_repo(name: str, path: Path) -> GitState:
    state = GitState(repo_name=name, repo_path=path, available=path.exists())
    if not state.available:
        state.error = f"Path not found: {path}"
        return state

    # Check if it's a git repo
    head = _git(["rev-parse", "--short", "HEAD"], path)
    if head is None:
        state.available = False
        state.error = "Not a git repository or git not available"
        return state

    state.head_commit = head
    state.branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)

    # Status — untracked, modified, staged
    status_raw = _git(["status", "--porcelain"], path)
    if status_raw:
        for line in status_raw.splitlines():
            if len(line) < 2:
                continue
            xy = line[:2]
            fname = line[3:].strip()
            if xy.startswith("??"):
                state.untracked.append(fname)
            elif xy[1] != " ":
                state.modified.append(fname)
            elif xy[0] != " ":
                state.staged.append(fname)

    # Ahead/behind origin
    ab = _git(["rev-list", "--left-right", "--count", f"{state.branch}...origin/{state.branch}"], path)
    if ab:
        state.ahead_behind = ab  # e.g. "2\t0" = 2 ahead, 0 behind

    return state


# ─── HTTP Probing ─────────────────────────────────────────────────────────────

async def probe_service_async(name: str, url: str) -> ServiceState:
    state = ServiceState(name=name, url=url, reachable=False)
    health_url = url.rstrip("/") + "/health"
    start = asyncio.get_event_loop().time()

    if HTTPX_AVAILABLE:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(health_url)
                elapsed = (asyncio.get_event_loop().time() - start) * 1000
                state.reachable = True
                state.status_code = resp.status_code
                state.response_ms = round(elapsed, 1)
                try:
                    body = resp.json()
                    state.health_detail = body
                    state.version = body.get("version") or body.get("v") or body.get("app_version")
                except Exception:
                    pass
        except Exception as e:
            state.error = str(e)[:120]
    else:
        # Fallback: urllib (sync, run in executor)
        import urllib.request as urlreq
        import time
        try:
            t0 = time.time()
            with urlreq.urlopen(health_url, timeout=HTTP_TIMEOUT) as r:
                state.reachable = True
                state.status_code = r.status
                state.response_ms = round((time.time() - t0) * 1000, 1)
        except Exception as e:
            state.error = str(e)[:120]

    return state

async def scan_services_async(services: Dict[str, str]) -> Dict[str, ServiceState]:
    tasks = [probe_service_async(name, url) for name, url in services.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for (name, _), result in zip(services.items(), results):
        if isinstance(result, Exception):
            out[name] = ServiceState(name=name, url=services[name], reachable=False, error=str(result))
        else:
            out[name] = result
    return out


# ─── Database Probing ─────────────────────────────────────────────────────────

def scan_librarian(db_path: Path) -> LibrarianState:
    state = LibrarianState(db_path=db_path, readable=db_path.exists())
    if not state.readable:
        state.error = f"DB not found: {db_path}"
        return state
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM architect_guidance")
        state.total_guidance = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM architect_guidance WHERE priority='current focus'")
        state.current_focus_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM architect_guidance WHERE priority='essence'")
        state.essence_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM architect_guidance WHERE embedding IS NOT NULL")
        embedded = c.fetchone()[0]
        if state.total_guidance > 0:
            state.embedding_coverage_pct = round(embedded / state.total_guidance * 100, 1)

        # Most recent handoff
        c.execute("""
            SELECT substr(content, 1, 200) FROM architect_guidance
            WHERE content LIKE '%PHOENIX%HANDOFF%' OR content LIKE '%HANDOFF%Instance%'
            ORDER BY created_at DESC LIMIT 1
        """)
        row = c.fetchone()
        if row:
            state.recent_handoff = row[0]

        conn.close()
    except Exception as e:
        state.error = str(e)
    return state


def scan_sapphire(db_path: Path) -> SapphireState:
    state = SapphireState(db_path=db_path, readable=db_path.exists())
    if not state.readable:
        state.error = f"DB not found: {db_path}"
        return state
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute("SELECT COUNT(*) FROM routing_observations")
            state.routing_observations = c.fetchone()[0]

            c.execute("SELECT query_text, observed_at FROM routing_observations ORDER BY observed_at DESC LIMIT 1")
            row = c.fetchone()
            if row:
                state.recent_observation = f"{row['observed_at']}: {row['query_text'][:80]}"
        except Exception:
            pass

        try:
            c.execute("SELECT COUNT(*) FROM detected_patterns")
            state.detected_patterns = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM detected_patterns WHERE adjustment_applied=0")
            state.unapplied_patterns = c.fetchone()[0]
        except Exception:
            pass

        conn.close()
    except Exception as e:
        state.error = str(e)
    return state


# ─── Filesystem Checks ────────────────────────────────────────────────────────

KEY_FILES = {
    "coach/APPENDIX_PERSISTENCE_NERVOUS_SYSTEM.md": REPOS["coach"] / "APPENDIX_PERSISTENCE_NERVOUS_SYSTEM.md",
    "coach/APPENDIX_PHASE_TRACKER.md":               REPOS["coach"] / "APPENDIX_PHASE_TRACKER.md",
    "omni/path_tau/README.md":                        REPOS["omni"] / "path_tau" / "README.md",
    "omni/path_tau/orchestrator/__init__.py":          REPOS["omni"] / "path_tau" / "orchestrator" / "orchestrator" / "__init__.py",
    "bridge/tau_integration.py":                      REPOS["bridge"] / "tau_integration.py",
    "bridge/cloud_eye_mcp_bridge.py":                 REPOS["bridge"] / "cloud_eye_mcp_bridge.py",
    "librarian_db":                                   LIBRARIAN_DB,
    "sapphire_db":                                    SAPPHIRE_DB,
}

def scan_filesystem() -> Dict[str, bool]:
    return {name: path.exists() for name, path in KEY_FILES.items()}


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def full_scan() -> RealitySnapshot:
    t0 = datetime.now(timezone.utc)

    # Run git and filesystem synchronously (fast, local)
    git_states = {name: scan_repo(name, path) for name, path in REPOS.items()}
    fs_state = scan_filesystem()
    lib_state = scan_librarian(LIBRARIAN_DB)
    sap_state = scan_sapphire(SAPPHIRE_DB)

    # Run HTTP probes concurrently
    svc_states = await scan_services_async(SERVICES)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds() * 1000

    return RealitySnapshot(
        scanned_at=t0.isoformat(),
        scan_duration_ms=round(elapsed, 1),
        git=git_states,
        services=svc_states,
        librarian=lib_state,
        sapphire=sap_state,
        filesystem=fs_state,
    )


def full_scan_sync() -> RealitySnapshot:
    """Synchronous wrapper for contexts without running event loop."""
    return asyncio.run(full_scan())
