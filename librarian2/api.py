"""
Librarian 2.0 — FastAPI Router
Exposes orientation endpoints for all Claude instances via HTTP.

Mount on cloud-eye-mcp-bridge:
    from librarian2.api import mount_librarian2
    mount_librarian2(app)

Or run standalone:
    python run_librarian2.py
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from scanner import full_scan, RealitySnapshot
from detector import detect_illusions
from engine import synthesize, OrientationBriefing


# ─── Cache (single-scan cache to avoid hammering services) ────────────────────
_cached_briefing: Optional[OrientationBriefing] = None
_cached_at: Optional[datetime] = None
CACHE_TTL_SECONDS = 60  # re-scan after 60s


async def _get_briefing(force_refresh: bool = False) -> OrientationBriefing:
    global _cached_briefing, _cached_at
    now = datetime.now(timezone.utc)
    if (
        not force_refresh
        and _cached_briefing is not None
        and _cached_at is not None
        and (now - _cached_at).total_seconds() < CACHE_TTL_SECONDS
    ):
        return _cached_briefing

    reality = await full_scan()
    claims = detect_illusions(reality)
    briefing = synthesize(reality, claims)
    _cached_briefing = briefing
    _cached_at = now
    return briefing


# ─── Router ───────────────────────────────────────────────────────────────────

def build_router():
    from fastapi import APIRouter
    router = APIRouter(prefix="/orient", tags=["librarian2"])

    @router.get("/briefing", response_class=PlainTextResponse,
                summary="Full orientation briefing — text format, ideal for instance startup")
    async def get_briefing_text(refresh: bool = Query(False, description="Force re-scan")):
        briefing = await _get_briefing(force_refresh=refresh)
        return PlainTextResponse(briefing.text_report)

    @router.get("/briefing.json",
                summary="Full orientation briefing — JSON format")
    async def get_briefing_json(refresh: bool = Query(False)):
        briefing = await _get_briefing(force_refresh=refresh)
        return JSONResponse({
            "generated_at": briefing.generated_at,
            "scan_duration_ms": briefing.scan_duration_ms,
            "warning_level": briefing.warning_level,
            "git": briefing.git_summary,
            "services": briefing.service_summary,
            "librarian": briefing.librarian_summary,
            "sapphire": briefing.sapphire_summary,
            "filesystem": briefing.filesystem_summary,
            "illusions": [
                {"type": c.claim_type, "claim": c.claim_text,
                 "severity": c.severity, "actual": c.actual_value,
                 "note": c.note}
                for c in briefing.illusions
            ],
            "unverifiable_count": len(briefing.unverifiable),
            "verified_count": len(briefing.verified_claims),
            "current_focus": briefing.current_focus_entries[:5],
            "work_order": briefing.active_work_order,
            "next_action": briefing.next_action,
            "text_report": briefing.text_report,
        })

    @router.get("/scan",
                summary="Raw reality snapshot — git, services, filesystem, DBs")
    async def get_scan(refresh: bool = Query(True)):
        briefing = await _get_briefing(force_refresh=refresh)
        # Return just the scan portion
        return JSONResponse({
            "scanned_at": briefing.generated_at,
            "duration_ms": briefing.scan_duration_ms,
            "git": briefing.git_summary,
            "services": briefing.service_summary,
            "filesystem": briefing.filesystem_summary,
        })

    @router.get("/illusions",
                summary="Illusion detection report — VERIFIED | ILLUSION | UNVERIFIABLE claims")
    async def get_illusions(refresh: bool = Query(False)):
        briefing = await _get_briefing(force_refresh=refresh)
        return JSONResponse({
            "warning_level": briefing.warning_level,
            "illusion_count": briefing.illusion_count,
            "illusions": [
                {"type": c.claim_type, "expected": c.expected_value,
                 "actual": c.actual_value, "severity": c.severity,
                 "claim": c.claim_text, "note": c.note}
                for c in briefing.illusions
            ],
            "unverifiable": [
                {"type": c.claim_type, "claim": c.claim_text, "note": c.note}
                for c in briefing.unverifiable[:10]
            ],
        })

    @router.get("/health",
                summary="Librarian 2.0 health check")
    async def health():
        return {"status": "ok", "version": "2.0.0",
                "description": "Persistence Nervous System — Illusion Detector"}

    return router


def mount_librarian2(app: FastAPI):
    """Mount Librarian 2.0 routes onto an existing FastAPI app."""
    router = build_router()
    app.include_router(router)
    print("[Librarian 2.0] Mounted at /orient/*")
