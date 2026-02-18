"""
Librarian 2.0 Extended Endpoints
=================================
Semantic search (all-MiniLM-L6-v2), guidance CRUD, briefing,
Phoenix Loop contribution endpoints, and health check.

Mount onto your FastAPI app:
    from librarian2_endpoints import mount_librarian2_endpoints
    mount_librarian2_endpoints(app)
"""

import os
import json
import uuid
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

# ── DB Path ──────────────────────────────────────────────────────────────────
LIBRARIAN_DB_PATH = os.environ.get("LIBRARIAN_DB_PATH", "librarian.db")

# ── Lazy embedding model ─────────────────────────────────────────────────────
_embedding_model = None
_embedding_model_loading = False

def get_embedding_model():
    """Lazy-load sentence-transformers all-MiniLM-L6-v2."""
    global _embedding_model, _embedding_model_loading
    if _embedding_model is not None:
        return _embedding_model
    if _embedding_model_loading:
        return None
    _embedding_model_loading = True
    try:
        from sentence_transformers import SentenceTransformer
        print("[LXR-LIBRARIAN] Loading embedding model...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[LXR-LIBRARIAN] Embedding model loaded: all-MiniLM-L6-v2")
        return _embedding_model
    except ImportError:
        print("[LXR-LIBRARIAN] sentence-transformers not installed. Run: pip install sentence-transformers")
        return None
    except Exception as e:
        print(f"[LXR-LIBRARIAN] Failed to load embedding model: {e}")
        return None
    finally:
        _embedding_model_loading = False

@contextmanager
def get_librarian_db():
    """Context manager for Librarian SQLite connections."""
    conn = sqlite3.connect(LIBRARIAN_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def _ensure_schema():
    """Create tables if they don't exist."""
    with get_librarian_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS architect_guidance (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                priority TEXT DEFAULT 'normal',
                category TEXT DEFAULT 'general',
                active INTEGER DEFAULT 1,
                embedding TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT DEFAULT 'exchange',
                embedding TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS routing_insights (
                id TEXT PRIMARY KEY,
                instance_number INTEGER,
                element TEXT,
                temperature REAL,
                skills_activated TEXT,
                semantic_score REAL,
                success INTEGER,
                insight TEXT,
                wuxing_phase TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY,
                instance_number INTEGER,
                what_was_done TEXT,
                what_remains TEXT,
                key_insight TEXT,
                files_modified TEXT,
                wuxing_phase TEXT,
                created_at TEXT NOT NULL
            )
        """)

def cosine_similarity(a, b) -> float:
    """Cosine similarity between two vectors."""
    import numpy as np
    if a is None or b is None:
        return 0.0
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

# ── Request Models ────────────────────────────────────────────────────────────
class LibrarianSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    search_guidance: bool = True
    search_memories: bool = True

class LibrarianGuidanceRequest(BaseModel):
    content: str
    priority: str = Field(default="normal")
    category: str = Field(default="general")

class ContributeInsightRequest(BaseModel):
    instance_number: int
    element: str
    temperature: float
    skills_activated: List[str]
    semantic_score: float = 0
    success: bool = True
    insight: str
    wuxing_phase: str = "earth"

class ContributeHandoffRequest(BaseModel):
    instance_number: int
    what_was_done: str
    what_remains: str
    key_insight: str
    files_modified: Optional[List[str]] = None
    wuxing_phase: str = "metal"

# ── Mount Function ────────────────────────────────────────────────────────────
def mount_librarian2_endpoints(app: FastAPI):
    """Attach all Librarian 2.0 extended endpoints to the given FastAPI app."""
    _ensure_schema()

    # ── /librarian/health ────────────────────────────────────────────────────
    @app.get("/librarian/health")
    def librarian_health():
        """Check Librarian DB connectivity and embedding status."""
        db_ok = False
        guidance_count = 0
        memory_count = 0
        embedded_guidance = 0
        try:
            with get_librarian_db() as conn:
                db_ok = True
                guidance_count = conn.execute(
                    "SELECT COUNT(*) FROM architect_guidance WHERE active=1"
                ).fetchone()[0]
                memory_count = conn.execute(
                    "SELECT COUNT(*) FROM memories"
                ).fetchone()[0]
                embedded_guidance = conn.execute(
                    "SELECT COUNT(*) FROM architect_guidance WHERE embedding IS NOT NULL"
                ).fetchone()[0]
        except Exception as e:
            print(f"[LXR-LIBRARIAN] Health check failed: {e}")
        model = get_embedding_model()
        return {
            "database_connected": db_ok,
            "database_path": LIBRARIAN_DB_PATH,
            "guidance_entries": guidance_count,
            "memory_entries": memory_count,
            "embedded_guidance": embedded_guidance,
            "embedding_model_loaded": model is not None,
            "embedding_model": "all-MiniLM-L6-v2" if model else "not loaded"
        }

    # ── /librarian/search ────────────────────────────────────────────────────
    @app.post("/librarian/search")
    def librarian_semantic_search(request: LibrarianSearchRequest):
        """
        Semantic search across guidance and memories.
        Falls back to keyword search if embeddings unavailable.
        Zero API cost — local all-MiniLM-L6-v2.
        """
        model = get_embedding_model()
        if model is None:
            return _keyword_search(request)
        try:
            query_embedding = model.encode(request.query).tolist()
            results = []
            with get_librarian_db() as conn:
                if request.search_guidance:
                    rows = conn.execute(
                        "SELECT id, content, priority, category, embedding, created_at "
                        "FROM architect_guidance WHERE embedding IS NOT NULL AND active=1"
                    ).fetchall()
                    for row in rows:
                        try:
                            stored = json.loads(row["embedding"])
                            sim = cosine_similarity(query_embedding, stored)
                            if sim >= request.threshold:
                                content = row["content"]
                                results.append({
                                    "type": "guidance",
                                    "id": row["id"],
                                    "content": content[:500] + "..." if len(content) > 500 else content,
                                    "priority": row["priority"],
                                    "category": row["category"],
                                    "similarity": round(sim, 3),
                                    "created_at": row["created_at"]
                                })
                        except (json.JSONDecodeError, TypeError):
                            continue
                if request.search_memories:
                    rows = conn.execute(
                        "SELECT id, content, type, embedding, created_at "
                        "FROM memories WHERE embedding IS NOT NULL"
                    ).fetchall()
                    for row in rows:
                        try:
                            stored = json.loads(row["embedding"])
                            sim = cosine_similarity(query_embedding, stored)
                            if sim >= request.threshold:
                                content = row["content"]
                                try:
                                    parsed = json.loads(content)
                                    preview = (f"Q: {parsed.get('user_message','')[:100]}... "
                                               f"A: {parsed.get('assistant_response','')[:100]}...")
                                except Exception:
                                    preview = content[:200] + "..."
                                results.append({
                                    "type": "memory",
                                    "id": row["id"],
                                    "content": preview,
                                    "memory_type": row["type"],
                                    "similarity": round(sim, 3),
                                    "created_at": row["created_at"]
                                })
                        except (json.JSONDecodeError, TypeError):
                            continue
            results.sort(key=lambda x: x["similarity"], reverse=True)
            results = results[:request.limit]
            return {
                "success": True,
                "query": request.query,
                "results": results,
                "total_matches": len(results),
                "threshold_used": request.threshold,
                "search_type": "semantic"
            }
        except Exception as e:
            print(f"[LXR-LIBRARIAN] Semantic search error: {e}")
            return {"success": False, "error": str(e), "results": [], "search_type": "semantic"}

    def _keyword_search(request: LibrarianSearchRequest):
        """Fallback keyword search when embeddings unavailable."""
        pattern = f"%{request.query}%"
        results = []
        with get_librarian_db() as conn:
            if request.search_guidance:
                rows = conn.execute(
                    "SELECT id, content, priority, category, created_at "
                    "FROM architect_guidance WHERE content LIKE ? AND active=1 "
                    "ORDER BY CASE priority WHEN 'current focus' THEN 1 WHEN 'essence' THEN 2 ELSE 3 END, created_at DESC "
                    "LIMIT ?",
                    (pattern, request.limit)
                ).fetchall()
                for row in rows:
                    content = row["content"]
                    results.append({
                        "type": "guidance",
                        "id": row["id"],
                        "content": content[:500] + "..." if len(content) > 500 else content,
                        "priority": row["priority"],
                        "category": row["category"],
                        "similarity": 0.5,
                        "created_at": row["created_at"]
                    })
            if request.search_memories and len(results) < request.limit:
                remaining = request.limit - len(results)
                rows = conn.execute(
                    "SELECT id, content, type, created_at FROM memories "
                    "WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (pattern, remaining)
                ).fetchall()
                for row in rows:
                    content = row["content"]
                    try:
                        parsed = json.loads(content)
                        preview = (f"Q: {parsed.get('user_message','')[:100]}... "
                                   f"A: {parsed.get('assistant_response','')[:100]}...")
                    except Exception:
                        preview = content[:200] + "..."
                    results.append({
                        "type": "memory",
                        "id": row["id"],
                        "content": preview,
                        "memory_type": row["type"],
                        "similarity": 0.5,
                        "created_at": row["created_at"]
                    })
        return {
            "success": True,
            "query": request.query,
            "results": results,
            "total_matches": len(results),
            "threshold_used": request.threshold,
            "search_type": "keyword"
        }

    # ── /librarian/search/keyword ────────────────────────────────────────────
    @app.post("/librarian/search/keyword")
    def librarian_keyword_search(request: LibrarianSearchRequest):
        """Explicit keyword-only search endpoint."""
        return _keyword_search(request)

    # ── /librarian/guidance GET ──────────────────────────────────────────────
    @app.get("/librarian/guidance")
    def list_librarian_guidance(
        priority: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20
    ):
        """List guidance entries from Librarian database."""
        with get_librarian_db() as conn:
            query = "SELECT id, content, priority, category, created_at FROM architect_guidance WHERE active=1"
            params = []
            if priority:
                query += " AND priority=?"
                params.append(priority)
            if category:
                query += " AND category=?"
                params.append(category)
            query += " ORDER BY CASE priority WHEN 'current focus' THEN 1 WHEN 'essence' THEN 2 ELSE 3 END, created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return {"success": True, "count": len(rows), "guidance": [dict(row) for row in rows]}

    # ── /librarian/guidance POST ─────────────────────────────────────────────
    @app.post("/librarian/guidance")
    def add_librarian_guidance(request: LibrarianGuidanceRequest):
        """
        Add new guidance entry to Librarian database.
        Auto-embeds for semantic search if model available.
        """
        guidance_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        embedding_json = None
        model = get_embedding_model()
        if model:
            try:
                embedding = model.encode(request.content).tolist()
                embedding_json = json.dumps(embedding)
            except Exception as e:
                print(f"[LXR-LIBRARIAN] Embedding failed: {e}")
        with get_librarian_db() as conn:
            if embedding_json:
                conn.execute(
                    "INSERT INTO architect_guidance (id, content, created_at, priority, category, active, embedding) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?)",
                    (guidance_id, request.content, created_at, request.priority, request.category, embedding_json)
                )
            else:
                conn.execute(
                    "INSERT INTO architect_guidance (id, content, created_at, priority, category, active) "
                    "VALUES (?, ?, ?, ?, ?, 1)",
                    (guidance_id, request.content, created_at, request.priority, request.category)
                )
        return {
            "success": True,
            "id": guidance_id,
            "created_at": created_at,
            "priority": request.priority,
            "category": request.category,
            "embedded": embedding_json is not None
        }

    # ── /librarian/briefing ──────────────────────────────────────────────────
    @app.get("/librarian/briefing")
    def get_librarian_briefing():
        """
        Get current project focus + essence wisdom for Cloud-Eye context.
        The ambient context injected into every query.
        """
        with get_librarian_db() as conn:
            focus_row = conn.execute(
                "SELECT id, content, created_at FROM architect_guidance "
                "WHERE priority='current focus' AND category='project' AND active=1 "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            essence_rows = conn.execute(
                "SELECT id, content, category FROM architect_guidance "
                "WHERE priority='essence' AND active=1 ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            handoff_rows = conn.execute(
                "SELECT id, content, created_at FROM architect_guidance "
                "WHERE priority='current focus' AND category='instance' AND active=1 "
                "ORDER BY created_at DESC LIMIT 3"
            ).fetchall()
        return {
            "success": True,
            "current_focus": dict(focus_row) if focus_row else None,
            "essence_wisdom": [dict(row) for row in essence_rows],
            "recent_handoffs": [dict(row) for row in handoff_rows],
            "retrieved_at": datetime.now().isoformat()
        }

    # ── /contribute-insight (Phoenix Loop) ──────────────────────────────────
    @app.post("/contribute-insight")
    def contribute_insight(request: ContributeInsightRequest):
        """
        Contribute a routing insight back to the Librarian.
        THE PHOENIX LOOP: Read → Work → Contribute → Next Instance Reads.
        """
        insight_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        with get_librarian_db() as conn:
            conn.execute(
                "INSERT INTO routing_insights "
                "(id, instance_number, element, temperature, skills_activated, "
                "semantic_score, success, insight, wuxing_phase, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    insight_id,
                    request.instance_number,
                    request.element,
                    request.temperature,
                    json.dumps(request.skills_activated),
                    request.semantic_score,
                    int(request.success),
                    request.insight,
                    request.wuxing_phase,
                    created_at
                )
            )
        return {"success": True, "id": insight_id, "created_at": created_at}

    # ── /contribute-handoff (Phoenix Loop formal end-of-instance) ────────────
    @app.post("/contribute-handoff")
    def contribute_handoff(request: ContributeHandoffRequest):
        """
        Write a phoenix-lite style handoff to the Librarian.
        The handoff is sacred because it is empty of you.
        """
        handoff_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        with get_librarian_db() as conn:
            conn.execute(
                "INSERT INTO handoffs "
                "(id, instance_number, what_was_done, what_remains, key_insight, "
                "files_modified, wuxing_phase, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    handoff_id,
                    request.instance_number,
                    request.what_was_done,
                    request.what_remains,
                    request.key_insight,
                    json.dumps(request.files_modified or []),
                    request.wuxing_phase,
                    created_at
                )
            )
        return {"success": True, "id": handoff_id, "created_at": created_at}

    # ── /routing-insights ────────────────────────────────────────────────────
    @app.get("/routing-insights")
    def get_routing_insights(element: Optional[str] = None, limit: int = 5):
        """Retrieve routing insights to inform future routing decisions."""
        with get_librarian_db() as conn:
            if element:
                rows = conn.execute(
                    "SELECT * FROM routing_insights WHERE element=? ORDER BY created_at DESC LIMIT ?",
                    (element, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM routing_insights ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return {"success": True, "count": len(rows), "insights": [dict(row) for row in rows]}
