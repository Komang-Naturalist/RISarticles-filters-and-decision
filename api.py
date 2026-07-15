"""FastAPI surface for validation, async screening jobs, progress, and exports."""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .export_excel import export as export_excel
from .export_html import export as export_html
from .export_prisma import export as export_prisma
from .slr_screening import parse_ris, screen_records, validate_records, write_ris

app = FastAPI(title="Lattice SLR API", version="0.1.0", docs_url="/backend/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

WORK_ROOT = Path(tempfile.gettempdir()) / "lattice-jobs"
WORK_ROOT.mkdir(exist_ok=True)
JOBS: dict[str, dict[str, Any]] = {}


class Override(BaseModel):
    record_id: str
    decision: str
    rationale: str
    reviewer: str
    previous_decision_id: str | None = None


@app.get("/backend/health")
def health() -> dict[str, Any]:
    return {"status": "healthy", "service": "lattice", "jobs": len(JOBS)}


@app.post("/backend/validate")
async def validate(file: UploadFile = File(...)) -> dict[str, Any]:
    records = parse_ris((await file.read()).decode("utf-8-sig", errors="replace"))
    issues = validate_records(records)
    return {"valid": bool(records) and not any(x["severity"] == "error" for x in issues), "records": len(records), "issues": issues}


@app.post("/backend/jobs", status_code=202)
async def create_job(background: BackgroundTasks, file: UploadFile = File(...), criteria: str = Form(...), concurrency: int = Form(20), low_confidence: float = Form(0.78)) -> dict[str, str]:
    job_id = uuid.uuid4().hex
    root = WORK_ROOT / job_id
    root.mkdir(parents=True)
    ris = root / "input.ris"
    ris.write_bytes(await file.read())
    (root / "criteria.md").write_text(criteria, encoding="utf-8")
    JOBS[job_id] = {"status": "queued", "progress": 0, "message": "Queued", "root": str(root)}
    background.add_task(run_job, job_id, ris, criteria, concurrency, low_confidence)
    return {"job_id": job_id, "events": f"/backend/jobs/{job_id}/events"}


async def run_job(job_id: str, ris: Path, criteria: str, concurrency: int, low_confidence: float) -> None:
    job = JOBS[job_id]
    try:
        job.update(status="running", progress=5, message="Validating RIS")
        records = parse_ris(ris.read_text(encoding="utf-8-sig", errors="replace"))
        if not records:
            raise ValueError("No valid RIS records found")
        job.update(progress=12, total=len(records), message="Screening abstracts")
        root = Path(job["root"])
        decisions = await screen_records(records, criteria, root, concurrency=concurrency, low_confidence=low_confidence)
        job.update(progress=78, message="Writing reproducible exports")
        write_ris(records, decisions, root)
        export_excel(root / "screening.jsonl", root / "hasil_screening.xlsx")
        export_html(root / "screening.jsonl", root / "dashboard.html")
        export_prisma(root / "manifest.json", root)
        job.update(status="completed", progress=100, message="Completed", artifacts=[p.name for p in root.iterdir() if p.is_file()])
    except Exception as exc:  # surfaced through job status without leaking secrets
        job.update(status="failed", message=str(exc), progress=100)


@app.get("/backend/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    return {key: value for key, value in JOBS[job_id].items() if key != "root"}


@app.get("/backend/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")

    async def stream():
        last = ""
        while True:
            payload = json.dumps({k: v for k, v in JOBS[job_id].items() if k != "root"})
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if JOBS[job_id]["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.6)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/backend/jobs/{job_id}/artifacts/{name}")
def artifact(job_id: str, name: str) -> FileResponse:
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    root = Path(JOBS[job_id]["root"]).resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, filename=path.name)


@app.post("/backend/projects/{project_id}/overrides")
def reviewer_override(project_id: str, override: Override) -> dict[str, Any]:
    if override.decision not in {"include", "exclude", "review"}:
        raise HTTPException(422, "Invalid decision")
    return {"id": uuid.uuid4().hex, "project_id": project_id, "event": "reviewer_override", **override.model_dump(), "immutable": True}
