"""PCB Parasitic Engine — FastAPI worker (Tier A).

Endpoints (all under /api):
    GET  /health                     — liveness + version
    POST /api/analyze                — multipart: pcb (file), f0 (optional, Hz)
    POST /api/inject                 — multipart: pcb (file) + selection JSON
                                       + project (zip, optional) OR cir / qsch (optional)
    GET  /api/report/{token}         — HTML engineering report
    GET  /api/download/{token}       — parasitic-injected project .zip
    DELETE /api/session/{token}      — wipe anonymous session data early

Sessions are anonymous and expire after TTL_SECONDS (default 1 h). Everything
lives under DATA_DIR (default /tmp/pcb-parasitic-sessions) — nothing leaves the host.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from pcb_engine import __version__, cir, field, pipeline

DATA_DIR = Path(os.environ.get("DATA_DIR", "/tmp/pcb-parasitic-sessions"))
TTL_SECONDS = int(os.environ.get("TTL_SECONDS", str(60 * 60)))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "64"))
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PCB Parasitic Engine", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])


# ---- rate limiting (simple per-IP token bucket) ----
_lock = threading.Lock()
_buckets: dict[str, tuple[float, float]] = {}
RATE_PER_MIN = float(os.environ.get("RATE_PER_MIN", "60"))


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _lock:
        tokens, ts = _buckets.get(ip, (RATE_PER_MIN, now))
        tokens = min(RATE_PER_MIN, tokens + (now - ts) * (RATE_PER_MIN / 60.0))
        if tokens < 1.0:
            _buckets[ip] = (tokens, now)
            return False
        _buckets[ip] = (tokens - 1.0, now)
        return True


@app.middleware("http")
async def guard(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and int(cl) > MAX_UPLOAD_MB * 1024 * 1024:
        return JSONResponse({"detail": f"upload too large (limit {MAX_UPLOAD_MB} MB)"}, status_code=413)
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if request.url.path.startswith("/api/") and not _rate_ok(ip):
        return JSONResponse({"detail": "rate limit exceeded — slow down"}, status_code=429)
    _cleanup_sessions()
    return await call_next(request)


_last_cleanup = 0.0


def _cleanup_sessions() -> None:
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < 60:
        return
    _last_cleanup = now
    for p in DATA_DIR.iterdir():
        if p.is_dir():
            meta = p / "meta.json"
            try:
                created = json.loads(meta.read_text())["created"] if meta.exists() else p.stat().st_mtime
            except Exception:
                created = p.stat().st_mtime
            if now - created > TTL_SECONDS:
                shutil.rmtree(p, ignore_errors=True)


def _mk_session() -> Path:
    sid = uuid.uuid4().hex
    d = DATA_DIR / sid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"created": time.time()}))
    return d


def _session_dir(token: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(404, "session not found")
    d = DATA_DIR / token
    if not d.exists():
        raise HTTPException(404, "session expired or not found (anonymous sessions live for 1 hour)")
    return d


@app.get("/health")
def health():
    return {"status": "ok", "service": "pcb-parasitic-engine", "version": __version__,
            "solver_tier": ("B (FastHenry2 field solve) available" if field.solver_info()["tier_b_available"]
                            else "A (closed-form) only"),
            "solvers": field.solver_info(),
            "data_dir": str(DATA_DIR),
            "session_ttl_s": TTL_SECONDS}


@app.post("/api/analyze")
async def analyze(pcb: UploadFile = File(...), f0: float = Form(50e6),
                  tier: str = Form("auto"), field_nets: str = Form("")):
    if not pcb.filename or not pcb.filename.lower().endswith(".kicad_pcb"):
        raise HTTPException(422, "upload a KiCad layout file (*.kicad_pcb)")
    data = await pcb.read()
    nets = [x.strip() for x in field_nets.split(",") if x.strip()]
    try:
        result = pipeline.analyze(data, pcb.filename, f0_hz=f0,
                                  tier=tier, field_nets=nets or None)
    except pipeline.PipelineError as exc:
        raise HTTPException(422, str(exc))
    result["source_file"] = pcb.filename
    return JSONResponse(result)


@app.post("/api/inject")
async def inject(pcb: UploadFile = File(...),
                 selection: str = Form(...),
                 project: UploadFile | None = File(None),
                 cir_file: UploadFile | None = File(None),
                 qsch_file: UploadFile | None = File(None),
                 ref_node: str = Form("0"),
                 design_name: str = Form("design"),
                 f0: float = Form(50e6),
                 tier: str = Form("auto")):
    try:
        sel = json.loads(selection)
        selected = list(sel.get("nets", sel if isinstance(sel, list) else []))
    except json.JSONDecodeError:
        raise HTTPException(422, "selection must be JSON: {\"nets\": [\"SW\", ...]}")
    if not selected:
        raise HTTPException(422, "select at least one net")

    pcb_bytes = await pcb.read()
    try:
        analysis = pipeline.analyze(pcb_bytes, pcb.filename or "board.kicad_pcb",
                                    f0_hz=f0, tier=tier,
                                    field_nets=list(selected) if tier.upper() == "B" else None)
    except pipeline.PipelineError as exc:
        raise HTTPException(422, str(exc))

    unknown = [n for n in selected if n not in {x["name"] for x in analysis["nets"]}]
    if unknown:
        raise HTTPException(422, f"nets not found in analysis: {', '.join(unknown)}")

    project_bytes = await project.read() if project and project.filename else None
    cir_bytes = await cir_file.read() if cir_file and cir_file.filename else None
    qsch_bytes = await qsch_file.read() if qsch_file and qsch_file.filename else None
    cir_text = None
    if cir_bytes is not None:
        try:
            cir_text = cir_bytes.decode("utf-8")
        except UnicodeDecodeError:
            cir_text = cir_bytes.decode("latin-1")

    if project_bytes is None and cir_text is None and qsch_bytes is None:
        raise HTTPException(422, "provide the QSPICE project (.zip) or a .cir/.qsch file to inject")

    try:
        result = pipeline.inject(project_bytes, cir_text, qsch_bytes, analysis, selected,
                                 ref_node=ref_node.strip() or "0",
                                 design_name=design_name,
                                 source_file=pcb.filename or "board.kicad_pcb")
    except pipeline.PipelineError as exc:
        raise HTTPException(422, str(exc))

    sess = _mk_session()
    out_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", design_name).strip("_") or "design"
    (sess / "out.zip").write_bytes(result["zip_bytes"])
    (sess / "report.html").write_text(result["report_html"], encoding="utf-8")
    (sess / "meta.json").write_text(json.dumps({"created": time.time(), "out_name": out_name}))

    return {"token": sess.name,
            "download": f"/api/download/{sess.name}",
            "report": f"/api/report/{sess.name}",
            "stats": result["stats"],
            "files_changed": result["files_changed"],
            "nets": selected}


@app.get("/api/download/{token}")
def download(token: str):
    d = _session_dir(token)
    meta = json.loads((d / "meta.json").read_text())
    name = f"{meta.get('out_name', 'design')}-parasitics.zip"
    return FileResponse(d / "out.zip", media_type="application/zip", filename=name)


@app.get("/api/report/{token}", response_class=HTMLResponse)
def report(token: str):
    d = _session_dir(token)
    return HTMLResponse((d / "report.html").read_text(encoding="utf-8"))


@app.delete("/api/session/{token}")
def wipe(token: str):
    d = _session_dir(token)
    shutil.rmtree(d, ignore_errors=True)
    return {"deleted": True}


# convenience: serve a minimal landing page so the worker itself isn't a dead end
@app.get("/", response_class=HTMLResponse)
def index():
    return f"""<!doctype html><title>PCB Parasitic Engine</title>
<style>body{{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;background:#0b2239;color:#d7edf2;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
main{{max-width:640px;padding:32px;background:#0f2c44;border-radius:14px}}code{{color:#7dd3fc}}h1{{font-size:20px}}a{{color:#38bdf8}}</style>
<main><h1>PCB Parasitic Engine — Tier A worker</h1>
<p>Health: <code><a href="/health">/health</a></code> · API docs: <code><a href="/docs">/docs</a></code></p>
<p>Upload your <code>.kicad_pcb</code> + QSPICE project via the web app — this service performs extraction (R, L, C) and writes the injected files.</p>
<p class="muted" style="color:#8fb3c0">v{__version__} · anonymous sessions · 1 h TTL</p></main>"""
