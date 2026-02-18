"""
Librarian 2.0 — Illusion Detector
Reads current-focus and recent guidance entries, extracts verifiable claims,
compares against the RealitySnapshot, and returns a list of discrepancies.

This is the core innovation: the Librarian can now see its own blindspots.

Wu Xing: Water — depth, hidden patterns, what flows beneath the surface.
"""
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

from config import LIBRARIAN_DB, SCAN_CURRENT_FOCUS_LIMIT, ILLUSION_RECENT_HOURS
from scanner import RealitySnapshot


# ─── Verdict Types ────────────────────────────────────────────────────────────

VERIFIED     = "VERIFIED"      # claim matches reality
ILLUSION     = "ILLUSION"      # claim contradicts reality
UNVERIFIABLE = "UNVERIFIABLE"  # cannot be checked automatically
STALE        = "STALE"         # claim may have been superseded

SEVERITY_HIGH   = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW    = "LOW"


@dataclass
class Claim:
    """A single extractable assertion from a guidance entry."""
    entry_id: str
    entry_priority: str
    claim_type: str          # git_commit | service_health | file_exists | bug_active | feature_enabled
    claim_text: str          # the raw claim sentence
    expected_value: str      # what the entry claims
    verdict: str             # VERIFIED | ILLUSION | UNVERIFIABLE | STALE
    actual_value: Optional[str] = None
    severity: str = SEVERITY_LOW
    note: Optional[str] = None


# ─── Claim Extractors ─────────────────────────────────────────────────────────

# Commit hash pattern (7–40 hex chars)
RE_COMMIT = re.compile(r'\b([0-9a-f]{7,40})\b')
# "master at abc1234" or "commit abc1234"
RE_COMMIT_CONTEXT = re.compile(r'(?:master|HEAD|branch|commit|at)\s+([0-9a-f]{7,10})\b', re.IGNORECASE)
# Service UP/DOWN
RE_SERVICE_UP = re.compile(r'(lxr-5|coach|cloudeye-lxr|cloudeye-ui)[^\n]*:\s*(UP|LIVE|healthy|running|operational)', re.IGNORECASE)
RE_SERVICE_DOWN = re.compile(r'(lxr-5|coach|cloudeye-lxr|cloudeye-ui)[^\n]*:\s*(DOWN|failed|error|unreachable)', re.IGNORECASE)
# Bug patterns  — "BUG 1: ..." or "no such table: ..." still present
RE_BUG_ACTIVE = re.compile(r'(?:BUG\s*\d+|no such table|no such column|attribute.*get|sqlite3\.Row).*', re.IGNORECASE)
# "fixed" or "resolved" near a bug description
RE_BUG_FIXED = re.compile(r'(?:fixed|resolved|patched|corrected)\b.{0,100}(?:bug|error|issue)', re.IGNORECASE)
# File path claims
RE_FILE_CLAIM = re.compile(r'(?:committed|deployed|created|exists|saved).*?([A-Za-z0-9_\-/\\]+\.(?:py|md|js|ts|jsx|sql|toml|json))\b', re.IGNORECASE)
# Untracked file mention
RE_UNTRACKED = re.compile(r'untracked files.*?:\s*(.+)', re.IGNORECASE)


def _service_name_normalize(raw: str) -> Optional[str]:
    raw = raw.lower()
    if "lxr-5" in raw or "lxr5" in raw:   return "lxr-5"
    if "coach" in raw:                      return "coach"
    if "cloudeye-lxr" in raw:              return "lxr"
    if "cloudeye-ui" in raw or "ui" in raw: return "ui"
    return None


def extract_claims(entry_id: str, priority: str, content: str) -> List[Claim]:
    claims: List[Claim] = []

    # 1. Git commit claims
    for m in RE_COMMIT_CONTEXT.finditer(content):
        commit = m.group(1).lower()
        claims.append(Claim(
            entry_id=entry_id,
            entry_priority=priority,
            claim_type="git_commit",
            claim_text=m.group(0),
            expected_value=commit,
            verdict=UNVERIFIABLE,  # filled in by verify()
        ))

    # 2. Service health claims  
    for m in RE_SERVICE_UP.finditer(content):
        sname = _service_name_normalize(m.group(1))
        if sname:
            claims.append(Claim(
                entry_id=entry_id,
                entry_priority=priority,
                claim_type="service_health",
                claim_text=m.group(0),
                expected_value=f"{sname}:UP",
                verdict=UNVERIFIABLE,
            ))

    # 3. Active bug claims (if entry is a "BEFORE STATE" or bug inventory)
    if re.search(r'BUG INVENTORY|KNOWN RUNTIME|BEFORE STATE|runtime bugs', content, re.IGNORECASE):
        for m in RE_BUG_ACTIVE.finditer(content):
            claims.append(Claim(
                entry_id=entry_id,
                entry_priority=priority,
                claim_type="bug_active",
                claim_text=m.group(0)[:120],
                expected_value="bug:present",
                verdict=UNVERIFIABLE,
                severity=SEVERITY_HIGH,
            ))

    # 4. File existence claims
    for m in RE_FILE_CLAIM.finditer(content):
        fname = m.group(1)
        if len(fname) > 4:  # skip trivial matches
            claims.append(Claim(
                entry_id=entry_id,
                entry_priority=priority,
                claim_type="file_exists",
                claim_text=m.group(0)[:120],
                expected_value=fname,
                verdict=UNVERIFIABLE,
            ))

    return claims


# ─── Verification ─────────────────────────────────────────────────────────────

def verify_claims(claims: List[Claim], reality: RealitySnapshot) -> List[Claim]:
    """Cross-reference each claim against the reality snapshot."""
    verified: List[Claim] = []

    for claim in claims:

        # ── git_commit ────────────────────────────────────────────────────────
        if claim.claim_type == "git_commit":
            matched = False
            for repo_name, git in reality.git.items():
                if git.head_commit and git.head_commit.lower().startswith(claim.expected_value.lower()):
                    claim.verdict = VERIFIED
                    claim.actual_value = git.head_commit
                    claim.note = f"Matches {repo_name} HEAD"
                    matched = True
                    break
            if not matched:
                # Check if any repo HEAD is different from the claimed commit
                actual_commits = {r: g.head_commit for r, g in reality.git.items() if g.head_commit}
                claim.verdict = ILLUSION
                claim.actual_value = str(actual_commits)
                claim.severity = SEVERITY_MEDIUM
                claim.note = "Commit not found as HEAD in any known repo"

        # ── service_health ────────────────────────────────────────────────────
        elif claim.claim_type == "service_health":
            sname, expected_status = claim.expected_value.split(":", 1)
            svc = reality.services.get(sname)
            if svc is None:
                claim.verdict = UNVERIFIABLE
                claim.note = f"Service '{sname}' not in scan scope"
            elif svc.reachable and expected_status == "UP":
                claim.verdict = VERIFIED
                claim.actual_value = f"HTTP {svc.status_code} ({svc.response_ms}ms)"
            elif not svc.reachable and expected_status == "DOWN":
                claim.verdict = VERIFIED
                claim.actual_value = f"Unreachable: {svc.error}"
            elif not svc.reachable and expected_status == "UP":
                claim.verdict = ILLUSION
                claim.actual_value = f"Service DOWN: {svc.error}"
                claim.severity = SEVERITY_HIGH
                claim.note = "Service claimed UP but is unreachable"
            else:
                claim.verdict = UNVERIFIABLE

        # ── bug_active ────────────────────────────────────────────────────────
        elif claim.claim_type == "bug_active":
            # We cannot automatically verify if a bug is fixed — mark as UNVERIFIABLE
            # but flag it with a note that it needs manual verification
            claim.verdict = UNVERIFIABLE
            claim.note = "Bug status requires code inspection or live test to verify"

        # ── file_exists ───────────────────────────────────────────────────────
        elif claim.claim_type == "file_exists":
            fname = claim.expected_value
            # Check our known filesystem scan first
            for key, exists in reality.filesystem.items():
                if fname.replace("\\", "/").lower() in key.lower() or key.lower() in fname.replace("\\", "/").lower():
                    if exists:
                        claim.verdict = VERIFIED
                        claim.actual_value = f"Found: {key}"
                    else:
                        claim.verdict = ILLUSION
                        claim.actual_value = f"NOT found: {key}"
                        claim.severity = SEVERITY_MEDIUM
                        claim.note = "File claimed to exist but not found on filesystem"
                    break
            else:
                claim.verdict = UNVERIFIABLE
                claim.note = "File not in known scan paths"

        verified.append(claim)

    return verified


# ─── Load from Librarian ──────────────────────────────────────────────────────

def load_current_focus_entries(db_path: Path = LIBRARIAN_DB) -> List[Tuple[str, str, str, str]]:
    """Returns list of (id, priority, category, content) for current-focus entries."""
    if not db_path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ILLUSION_RECENT_HOURS)).isoformat()
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        c = conn.cursor()
        c.execute("""
            SELECT id, priority, category, content
            FROM architect_guidance
            WHERE priority IN ('current focus', 'current_focus', 'essence')
            AND (created_at > ? OR priority LIKE '%current%')
            ORDER BY
              CASE priority WHEN 'current focus' THEN 0 WHEN 'current_focus' THEN 0 ELSE 1 END,
              created_at DESC
            LIMIT ?
        """, (cutoff, SCAN_CURRENT_FOCUS_LIMIT + 10))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


# ─── Main API ─────────────────────────────────────────────────────────────────

def detect_illusions(reality: RealitySnapshot) -> List[Claim]:
    """
    Full illusion detection pass:
    1. Load current-focus + recent essence entries
    2. Extract verifiable claims
    3. Cross-reference against reality
    4. Return sorted list: ILLUSION first, then UNVERIFIABLE, then VERIFIED
    """
    entries = load_current_focus_entries()
    all_claims: List[Claim] = []

    for entry_id, priority, category, content in entries:
        claims = extract_claims(str(entry_id), priority, content)
        all_claims.extend(claims)

    # Deduplicate by (claim_type, expected_value)
    seen = set()
    unique_claims: List[Claim] = []
    for c in all_claims:
        key = (c.claim_type, c.expected_value[:40])
        if key not in seen:
            seen.add(key)
            unique_claims.append(c)

    verified = verify_claims(unique_claims, reality)

    # Sort: ILLUSION > UNVERIFIABLE > VERIFIED, then by severity
    sev_order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    verdict_order = {ILLUSION: 0, UNVERIFIABLE: 1, VERIFIED: 2, STALE: 3}

    return sorted(verified, key=lambda c: (verdict_order.get(c.verdict, 9), sev_order.get(c.severity, 9)))
