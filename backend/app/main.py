from __future__ import annotations

import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import settings
from .export_utils import result_to_csv_bytes, result_to_json_bytes
from .models import TaskEnvelope, UploadResponse
from .pipeline import process_annual_report


app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TASK_STORE: dict[str, TaskEnvelope] = {}
settings.upload_dir.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "qwen_enabled": bool(settings.qwen_api_key and settings.qwen_base_url and settings.qwen_model),
    }


@app.post("/api/upload", response_model=UploadResponse)
async def upload_report(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="??? PDF ?????")

    data = await file.read()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(data) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"?????????? {settings.max_upload_size_mb} MB?",
        )

    task_id = str(uuid.uuid4())
    target_path = settings.upload_dir / f"{task_id}.pdf"
    target_path.write_bytes(data)

    result = process_annual_report(target_path)
    envelope = TaskEnvelope(task_id=task_id, result=result)
    TASK_STORE[task_id] = envelope
    return UploadResponse(task_id=task_id)


@app.get("/api/result/{task_id}", response_model=TaskEnvelope)
def get_result(task_id: str) -> TaskEnvelope:
    envelope = TASK_STORE.get(task_id)
    if not envelope:
        raise HTTPException(status_code=404, detail="??????????")
    return envelope


@app.get("/api/export/{task_id}")
def export_result(task_id: str, format: str = "json") -> Response:
    envelope = TASK_STORE.get(task_id)
    if not envelope:
        raise HTTPException(status_code=404, detail="??????????")

    normalized = format.lower()
    if normalized == "json":
        return Response(
            content=result_to_json_bytes(envelope.result),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{task_id}.json"'},
        )
    if normalized == "csv":
        return Response(
            content=result_to_csv_bytes(envelope.result),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{task_id}.csv"'},
        )
    raise HTTPException(status_code=400, detail="format ??? json ? csv?")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "??????????????????"}
