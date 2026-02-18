"""
Librarian 2.0 — Configuration
Ubuntu Wu Xing Wuji Neigong Lineage
"""
import os
from pathlib import Path

# ─── Database Paths ───────────────────────────────────────────────────────────
LIBRARIAN_DB = Path(os.environ.get(
    "LIBRARIAN_DB_PATH",
    r"C:\Users\grego\Desktop\LearningWorkflow\librarian.db"
))

SAPPHIRE_DB = Path(os.environ.get(
    "SAPPHIRE_DB_PATH",
    r"C:\Users\grego\Desktop\LearningWorkflow\sapphire_torus.db"
))

# ─── Known Repos ──────────────────────────────────────────────────────────────
REPOS = {
    "coach":  Path(r"C:\Users\grego\Desktop\CloudEye\production\cloudeye-coach"),
    "lxr-5":  Path(r"C:\Users\grego\Desktop\CloudEye\production\lxr-5"),
    "lxr":    Path(r"C:\Users\grego\Desktop\CloudEye\production\cloudeye-lxr-railway"),
    "ui":     Path(r"C:\Users\grego\Desktop\CloudEye\production\cloudeye-ui"),
    "omni":   Path(r"C:\Users\grego\Desktop\CloudEye\production\omni-os-blueprint"),
    "bridge": Path(r"C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge"),
}

# ─── Railway Services ─────────────────────────────────────────────────────────
SERVICES = {
    "lxr-5":    "https://lxr-5-production.up.railway.app",
    "coach":    "https://cloudeye-coach-production.up.railway.app",
    "coach-fe": "https://coach-frontend-production.up.railway.app",
    "ui":       "https://cloudeye-ui-production.up.railway.app",
    "lxr":      "https://cloudeye-lxr-production.up.railway.app",
}

# ─── Scanning ─────────────────────────────────────────────────────────────────
HTTP_TIMEOUT = 8          # seconds per service probe
SCAN_CURRENT_FOCUS_LIMIT = 20   # how many current-focus entries to analyse
SCAN_ESSENCE_LIMIT = 10         # top essence entries to include in briefing
ILLUSION_RECENT_HOURS = 72      # only scan entries from the last N hours for illusions

# ─── API ──────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("LIBRARIAN2_PORT", 8556))
