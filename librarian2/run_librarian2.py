"""
Librarian 2.0 — Standalone Launcher

Usage:
    python run_librarian2.py                  # Start server on port 8556
    python run_librarian2.py --once           # Single scan, print report, exit
    python run_librarian2.py --once --json    # Single scan, JSON output
    python run_librarian2.py --port 8556      # Custom port

Environment variables:
    LIBRARIAN_DB_PATH     Path to librarian.db
    SAPPHIRE_DB_PATH      Path to sapphire_torus.db
    LIBRARIAN2_PORT       HTTP port (default 8556)
"""
import sys
import asyncio
import argparse


def run_once(as_json: bool = False):
    """Perform a single scan and print the report, then exit."""
    from scanner import full_scan
    from detector import detect_illusions
    from engine import synthesize
    import json as jsonlib

    async def _run():
        reality = await full_scan()
        claims = detect_illusions(reality)
        briefing = synthesize(reality, claims)
        return briefing

    briefing = asyncio.run(_run())

    if as_json:
        import json as jlib
        out = {
            "generated_at": briefing.generated_at,
            "warning_level": briefing.warning_level,
            "illusion_count": briefing.illusion_count,
            "git": briefing.git_summary,
            "services": briefing.service_summary,
            "filesystem": briefing.filesystem_summary,
            "work_order": briefing.active_work_order,
            "next_action": briefing.next_action,
        }
        print(jlib.dumps(out, indent=2))
    else:
        print(briefing.text_report)


def run_server(port: int = 8556):
    """Start the FastAPI server."""
    from fastapi import FastAPI
    from api import mount_librarian2
    import uvicorn

    app = FastAPI(
        title="Librarian 2.0",
        description="Persistence Nervous System — Reality Scanner + Illusion Detector",
        version="2.0.0",
    )

    mount_librarian2(app)

    # Also serve a root redirect
    from fastapi.responses import RedirectResponse
    @app.get("/")
    async def root():
        return RedirectResponse("/orient/briefing")

    print(f"""
╔══════════════════════════════════════════════════════╗
║  LIBRARIAN 2.0  —  Persistence Nervous System        ║
║  Serving at http://localhost:{port}                    ║
║                                                      ║
║  Endpoints:                                          ║
║    GET /orient/briefing      → text orientation      ║
║    GET /orient/briefing.json → JSON orientation      ║
║    GET /orient/scan          → reality scan only     ║
║    GET /orient/illusions     → illusion report       ║
║    GET /orient/health        → health check          ║
╚══════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Librarian 2.0")
    parser.add_argument("--once", action="store_true", help="Single scan and exit")
    parser.add_argument("--json", action="store_true", help="Output JSON (--once only)")
    parser.add_argument("--port", type=int, default=8556, help="HTTP port for server mode")
    args = parser.parse_args()

    if args.once:
        run_once(as_json=args.json)
    else:
        run_server(port=args.port)
