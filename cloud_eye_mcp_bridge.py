import os
import subprocess
import httpx
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Cloud-Eye MCP Bridge", version="0.3.0")

# ── Librarian 2.0 — Persistence Nervous System ──────────────────────────────
try:
    from librarian2.api import mount_librarian2
    mount_librarian2(app)
    print("[OK] Librarian 2.0 mounted")
except ImportError:
    print("[WARN] Librarian 2.0 not available — librarian2/ package not found")

# ── Librarian 2.0 Extended Endpoints (semantic search, guidance, briefing) ──
try:
    from librarian2_endpoints import mount_librarian2_endpoints
    mount_librarian2_endpoints(app)
    print("[OK] Librarian 2.0 extended endpoints mounted")
except ImportError:
    print("[WARN] Librarian 2.0 extended endpoints not available")

# ── PowerShell Bridge — Defensive .bat Execution Layer ──────────────────────
try:
    from powershell_bridge.router import router as ps_router
    app.include_router(ps_router, prefix="/powershell")
    print("[OK] PowerShell Bridge mounted at /powershell")
except ImportError:
    print("[WARN] PowerShell Bridge not available — powershell_bridge/ package not found")

# ============================================================================
# Security
# ============================================================================
API_TOKEN = os.environ.get("CLOUD_EYE_API_TOKEN", "wuji-neigong-2026")

async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid API token")

# ============================================================================
# Git Models & Helpers
# ============================================================================
class GitCommitRequest(BaseModel):
    message: str
    repo_path: Optional[str] = None

class GitPushRequest(BaseModel):
    remote: str = "origin"
    branch: str = "main"
    repo_path: Optional[str] = None

class FileReadRequest(BaseModel):
    path: str
    repo_path: Optional[str] = None

class FileWriteRequest(BaseModel):
    path: str
    content: str
    repo_path: Optional[str] = None

class RailwayQueryRequest(BaseModel):
    query: str
    variables: dict = {}

class RailwayDeploymentRequest(BaseModel):
    project_id: Optional[str] = None
    limit: int = 5

def get_repo_path(custom_path: Optional[str] = None) -> Path:
    if custom_path:
        return Path(custom_path).resolve()
    return Path.cwd()

# ============================================================================
# Endpoints
# ============================================================================
@app.get("/health")
def health_check():
    return {
        "status": "atmospheric",
        "element": "water",
        "flow": "ready",
        "version": "0.3.0",
        "modules": {
            "librarian2": "active",
            "librarian2_endpoints": "active",
            "powershell_bridge": "active"
        }
    }

@app.get("/git/status")
def git_status(repo_path: Optional[str] = None, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {API_TOKEN}": return {"error": "Unauthorized"}
    try:
        path = get_repo_path(repo_path)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )
        return {
            "status": result.stdout,
            "clean": len(result.stdout.strip()) == 0,
            "returncode": result.returncode
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/git/commit")
def git_commit(req: GitCommitRequest, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {API_TOKEN}": return {"error": "Unauthorized"}
    try:
        path = get_repo_path(req.repo_path)
        subprocess.run(["git", "add", "."], cwd=path, check=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", req.message],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "message": req.message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/git/push")
def git_push(req: GitPushRequest, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {API_TOKEN}": return {"error": "Unauthorized"}
    try:
        path = get_repo_path(req.repo_path)
        result = subprocess.run(
            ["git", "push", req.remote, req.branch],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout + result.stderr
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/fs/read")
def fs_read(req: FileReadRequest, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {API_TOKEN}": return {"error": "Unauthorized"}
    try:
        base = get_repo_path(req.repo_path)
        file_path = (base / req.path).resolve()
        if not str(file_path).startswith(str(base)):
            raise HTTPException(status_code=403, detail="Path traversal not allowed")
        content = file_path.read_text(encoding="utf-8")
        return {"path": req.path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/fs/write")
def fs_write(req: FileWriteRequest, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {API_TOKEN}": return {"error": "Unauthorized"}
    try:
        base = get_repo_path(req.repo_path)
        file_path = (base / req.path).resolve()
        if not str(file_path).startswith(str(base)):
            raise HTTPException(status_code=403, detail="Path traversal not allowed")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(req.content, encoding="utf-8")
        return {"path": req.path, "success": True, "size": len(req.content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/railway/query")
async def railway_graphql(req: RailwayQueryRequest, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {API_TOKEN}": return {"error": "Unauthorized"}
    token = os.environ.get("RAILWAY_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="RAILWAY_TOKEN not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://backboard.railway.app/graphql/v2",
            json={"query": req.query, "variables": req.variables},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15.0
        )
        return resp.json()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
