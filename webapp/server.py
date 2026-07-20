"""FastAPI backend that wraps the wp-migrator pipeline behind a small web UI.

This is a LOCAL, single-user tool. Secrets stay server-side in env vars
(ANTHROPIC_API_KEY, WP_APP_PASSWORD); the browser never sees them. Jobs run in
background threads with an in-memory store — restart the server and jobs are
gone (their WXR files remain on disk until you delete the temp dir).
"""
from __future__ import annotations

import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from wpmigrate import sitemap
from wpmigrate.config import DEFAULT_MODEL, Config, validate
from wpmigrate.fetch import Fetcher
from wpmigrate.pipeline import run

app = FastAPI(title="wp-migrator")

_STATIC = Path(__file__).parent / "static"
_WORK = Path(tempfile.gettempdir()) / "wp-migrator-jobs"
_WORK.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Job store
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    id: str
    status: str = "running"          # running | done | error
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    events: list[dict] = field(default_factory=list)
    wxr_path: Path | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_JOBS: dict[str, Job] = {}


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class SitemapReq(BaseModel):
    sitemap_url: str


class JobReq(BaseModel):
    urls: list[str]
    image_mode: str = "sideload"     # sideload | remote | bundle | upload
    post_type: str = "page"
    post_status: str = "publish"
    author: str = "admin"
    model: str = ""
    wp_base_url: str = ""
    wp_user: str = ""
    selectors: dict[str, str] = {}
    render: bool = False              # headless-browser (Playwright) rendering


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.post("/api/sitemap")
def api_sitemap(req: SitemapReq) -> dict:
    fetcher = Fetcher(
        user_agent="wp-migrator/0.1 (+sitemap discovery)",
        timeout=30.0,
        rate_limit_seconds=0.5,
    )
    try:
        urls = sitemap.discover(fetcher, req.sitemap_url.strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        fetcher.close()
    return {"count": len(urls), "urls": urls}


@app.post("/api/jobs")
def api_create_job(req: JobReq) -> dict:
    urls = [u.strip() for u in req.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = _WORK / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    urls_file = job_dir / "urls.txt"
    urls_file.write_text("\n".join(urls), encoding="utf-8")
    out_file = job_dir / "export.wxr"

    cfg = Config(
        urls_file=urls_file,
        out_file=out_file,
        selectors=req.selectors or {},
        image_dir=job_dir / "images",
        post_type=req.post_type,
        post_status=req.post_status,
        author=req.author or "admin",
        image_mode=req.image_mode,
        wp_base_url=req.wp_base_url.rstrip("/"),
        wp_user=req.wp_user,
        wp_app_password=os.environ.get("WP_APP_PASSWORD", ""),
        model=req.model.strip()
        or os.environ.get("WPMIGRATE_MODEL", DEFAULT_MODEL),
        render=req.render,
    )

    problems = validate(cfg)
    if problems:
        raise HTTPException(status_code=400, detail=problems)

    job = Job(id=job_id)
    _JOBS[job_id] = job

    def worker() -> None:
        def progress(event: dict) -> None:
            with job.lock:
                if event["type"] == "start":
                    job.total = event["total"]
                elif event["type"] == "page":
                    job.events.append(event)
                elif event["type"] == "done":
                    job.succeeded = event["succeeded"]
                    job.failed = event["failed"]

        try:
            run(cfg, progress=progress)
            with job.lock:
                job.wxr_path = out_file if out_file.exists() else None
                job.status = "done"
        except Exception as exc:  # surface fatal setup/runtime errors to the UI
            with job.lock:
                job.status = "error"
                job.error = str(exc)

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job.")
    with job.lock:
        return {
            "id": job.id,
            "status": job.status,
            "total": job.total,
            "succeeded": job.succeeded,
            "failed": job.failed,
            "events": job.events,
            "error": job.error,
            "has_download": job.wxr_path is not None,
        }


@app.get("/api/jobs/{job_id}/download")
def api_download(job_id: str) -> FileResponse:
    job = _JOBS.get(job_id)
    if job is None or job.wxr_path is None or not job.wxr_path.exists():
        raise HTTPException(status_code=404, detail="No WXR available for this job.")
    return FileResponse(
        job.wxr_path,
        media_type="application/xml",
        filename="export.wxr",
    )
