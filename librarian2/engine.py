"""
Librarian 2.0 — Orientation Engine
Synthesizes the Reality Snapshot + Illusion Detection into a single,
grounded briefing that a new instance can act on immediately.

Wu Xing: Earth — synthesis, grounding, integration. What is actually here.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .config import LIBRARIAN_DB, SCAN_ESSENCE_LIMIT, SAPPHIRE_DB
from .scanner import RealitySnapshot, GitState, ServiceState
from .detector import Claim, VERIFIED, ILLUSION, UNVERIFIABLE, SEVERITY_HIGH, SEVERITY_MEDIUM


@dataclass
class OrientationBriefing:
    generated_at: str
    scan_duration_ms: float

    # Ground truth
    git_summary: Dict[str, str]          # repo → "abc1234 (master, clean)"
    service_summary: Dict[str, str]      # svc → "UP 200ms" or "DOWN"
    librarian_summary: str
    sapphire_summary: str
    filesystem_summary: Dict[str, bool]

    # Illusion report
    illusions: List[Claim]
    unverifiable: List[Claim]
    verified_claims: List[Claim]
    illusion_count: int
    warning_level: str                   # GREEN | AMBER | RED

    # Grounded guidance
    current_focus_entries: List[Dict]    # top N from DB, content + metadata
    essence_snapshot: List[str]          # top N essence entry previews
    active_work_order: str               # synthesized plain-text work order
    next_action: str                     # single clearest next step

    # Raw text briefing (for direct display)
    text_report: str = ""


def _git_line(name: str, g: GitState) -> str:
    if not g.available:
        return f"{name}: NOT FOUND — {g.error}"
    if g.head_commit is None:
        return f"{name}: not a git repo"
    status = []
    if g.staged:    status.append(f"{len(g.staged)} staged")
    if g.modified:  status.append(f"{len(g.modified)} modified")
    if g.untracked: status.append(f"{len(g.untracked)} untracked")
    clean = "clean" if not status else ", ".join(status)
    ab = f" [{g.ahead_behind}]" if g.ahead_behind and g.ahead_behind != "0\t0" else ""
    return f"{name}: {g.head_commit} ({g.branch or '?'}, {clean}){ab}"


def _svc_line(name: str, s: ServiceState) -> str:
    if s.reachable:
        v = f" v{s.version}" if s.version else ""
        return f"{name}: ✓ UP {s.response_ms}ms{v}"
    return f"{name}: ✗ DOWN — {s.error or 'unreachable'}"


def _load_current_focus(db_path: Path, limit: int = 8) -> List[Dict]:
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT id, priority, category, substr(content, 1, 400) AS preview,
                   created_at
            FROM architect_guidance
            WHERE priority IN ('current focus', 'current_focus')
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        return [{"error": str(e)}]


def _load_essence_snapshot(db_path: Path, limit: int = SCAN_ESSENCE_LIMIT) -> List[str]:
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        c = conn.cursor()
        c.execute("""
            SELECT substr(content, 1, 200)
            FROM architect_guidance
            WHERE priority = 'essence'
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = [r[0] for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _derive_work_order(reality: RealitySnapshot, illusions: List[Claim]) -> tuple:
    """
    Derive a plain-English work order and next action from reality.
    Returns (work_order_text, next_action_text).
    """
    lines = []
    next_action = "Review current focus entries in Librarian and orient to system state."

    # Critical: any service DOWN?
    down_svcs = [name for name, s in reality.services.items() if not s.reachable]
    if down_svcs:
        lines.append(f"⚠ CRITICAL: Services unreachable: {', '.join(down_svcs)}")
        next_action = f"Investigate why {down_svcs[0]} is unreachable — check Railway logs"

    # High-severity illusions
    high_illusions = [c for c in illusions if c.verdict == ILLUSION and c.severity == SEVERITY_HIGH]
    if high_illusions:
        for ill in high_illusions[:3]:
            lines.append(f"⚠ ILLUSION ({ill.claim_type}): {ill.claim_text[:80]} → actually: {ill.actual_value}")

    # Untracked files in coach repo
    coach_git = reality.git.get("coach")
    if coach_git and coach_git.untracked:
        lines.append(f"🟡 {len(coach_git.untracked)} untracked files in coach repo — commit or discard:")
        for f in coach_git.untracked[:4]:
            lines.append(f"   {f}")

    # Bonsai Forge status
    forge_exists = reality.filesystem.get("omni/path_tau/README.md", False)
    if not forge_exists:
        lines.append("🟡 Bonsai Forge (Path Tau) scaffold NOT committed to omni-os-blueprint")
        if next_action.startswith("Review"):
            next_action = "Download path_tau_scaffold.ps1 from Telegram (~msg 622), execute, commit to omni-os-blueprint"

    # PNS appendix
    pns_exists = reality.filesystem.get("coach/APPENDIX_PERSISTENCE_NERVOUS_SYSTEM.md", False)
    if not pns_exists:
        lines.append("🟡 APPENDIX_PERSISTENCE_NERVOUS_SYSTEM.md not yet committed to coach repo")
        if next_action.startswith("Review"):
            next_action = "Commit APPENDIX_PERSISTENCE_NERVOUS_SYSTEM.md to cloudeye-coach (file in Telegram msg 639)"

    # All green?
    if not lines and not down_svcs:
        lines.append("✅ No critical issues detected. System appears healthy.")
        next_action = "Proceed with current focus: LXR-5 bridge bug fix (4 SQL errors)"

    return "\n".join(lines), next_action


def _warning_level(illusions: List[Claim], down_svcs: List[str]) -> str:
    if down_svcs or any(c.severity == SEVERITY_HIGH for c in illusions if c.verdict == ILLUSION):
        return "RED"
    if any(c.severity == SEVERITY_MEDIUM for c in illusions if c.verdict == ILLUSION):
        return "AMBER"
    return "GREEN"


def _build_text_report(briefing: "OrientationBriefing") -> str:
    ts = briefing.generated_at[:19].replace("T", " ")
    lines = [
        f"╔══════════════════════════════════════════════════════════════════╗",
        f"║  LIBRARIAN 2.0 — ORIENTATION BRIEFING                           ║",
        f"║  {ts} UTC    scan: {briefing.scan_duration_ms:.0f}ms    ║",
        f"╚══════════════════════════════════════════════════════════════════╝",
        f"",
        f"── REALITY SCAN ─────────────────────────────────────────────────",
    ]

    lines.append("GIT REPOS:")
    for repo, summary in briefing.git_summary.items():
        lines.append(f"  {summary}")

    lines.append("\nRAILWAY SERVICES:")
    for svc, summary in briefing.service_summary.items():
        lines.append(f"  {summary}")

    lines.append(f"\nLIBRARIAN DB: {briefing.librarian_summary}")
    lines.append(f"SAPPHIRE DB:  {briefing.sapphire_summary}")

    lines.append("\nKEY FILES:")
    for fname, exists in briefing.filesystem_summary.items():
        icon = "✓" if exists else "✗"
        lines.append(f"  {icon} {fname}")

    # Illusions
    lines.append(f"\n── ILLUSION REPORT  [{briefing.warning_level}] ──────────────────────────────")
    if not briefing.illusions:
        lines.append("  ✅ No confirmed illusions detected.")
    else:
        for ill in briefing.illusions[:6]:
            lines.append(f"  ⚠ [{ill.severity}] {ill.claim_type}: {ill.claim_text[:70]}")
            if ill.actual_value:
                lines.append(f"     actual: {ill.actual_value[:70]}")

    if briefing.unverifiable:
        lines.append(f"\n  UNVERIFIABLE ({len(briefing.unverifiable)} claims — require manual check):")
        for u in briefing.unverifiable[:4]:
            lines.append(f"    ? {u.claim_type}: {u.claim_text[:70]}")
            if u.note:
                lines.append(f"      note: {u.note}")

    # Work Order
    lines.append(f"\n── ACTIVE WORK ORDER ────────────────────────────────────────────")
    lines.append(briefing.active_work_order)

    lines.append(f"\n── NEXT ACTION ──────────────────────────────────────────────────")
    lines.append(f"  → {briefing.next_action}")

    # Current Focus (top 3)
    if briefing.current_focus_entries:
        lines.append(f"\n── CURRENT FOCUS (latest {min(3, len(briefing.current_focus_entries))}) ────────────────────────────────────")
        for entry in briefing.current_focus_entries[:3]:
            if "error" in entry:
                continue
            lines.append(f"\n  [{entry.get('created_at', '')[:16]}] [{entry.get('category', '')}]")
            lines.append(f"  {entry.get('preview', '')[:300]}")

    lines.append(f"\n{'═'*68}")
    lines.append("  The Dragon who reads this sees what is real, not what was recorded.")
    lines.append(f"{'═'*68}")

    return "\n".join(lines)


# ─── Main API ─────────────────────────────────────────────────────────────────

def synthesize(reality: RealitySnapshot, illusion_claims: List[Claim]) -> OrientationBriefing:
    """Build the full OrientationBriefing from a reality snapshot and illusion report."""

    git_summary = {name: _git_line(name, g) for name, g in reality.git.items()}
    svc_summary = {name: _svc_line(name, s) for name, s in reality.services.items()}

    lib = reality.librarian
    lib_summary = (
        f"{lib.total_guidance} entries ({lib.current_focus_count} focus, {lib.essence_count} essence), "
        f"{lib.embedding_coverage_pct}% embedded"
        if lib.readable else f"UNAVAILABLE — {lib.error}"
    )

    sap = reality.sapphire
    sap_summary = (
        f"{sap.routing_observations} observations, {sap.unapplied_patterns} unapplied patterns"
        if sap.readable else f"UNAVAILABLE — {sap.error}"
    )

    illusions   = [c for c in illusion_claims if c.verdict == ILLUSION]
    unverif     = [c for c in illusion_claims if c.verdict == UNVERIFIABLE]
    verified    = [c for c in illusion_claims if c.verdict == VERIFIED]

    down_svcs   = [name for name, s in reality.services.items() if not s.reachable]
    warn_level  = _warning_level(illusions, down_svcs)

    current_focus = _load_current_focus(LIBRARIAN_DB)
    essence_snap  = _load_essence_snapshot(LIBRARIAN_DB)

    work_order, next_action = _derive_work_order(reality, illusion_claims)

    briefing = OrientationBriefing(
        generated_at=reality.scanned_at,
        scan_duration_ms=reality.scan_duration_ms,
        git_summary=git_summary,
        service_summary=svc_summary,
        librarian_summary=lib_summary,
        sapphire_summary=sap_summary,
        filesystem_summary=reality.filesystem,
        illusions=illusions,
        unverifiable=unverif,
        verified_claims=verified,
        illusion_count=len(illusions),
        warning_level=warn_level,
        current_focus_entries=current_focus,
        essence_snapshot=essence_snap,
        active_work_order=work_order,
        next_action=next_action,
    )

    briefing.text_report = _build_text_report(briefing)
    return briefing
