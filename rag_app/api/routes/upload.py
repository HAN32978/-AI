"""接收原件并持久化任务；HTTP 202 表示已接收，不表示已完成解析。"""
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from config.settings import settings
from core.document_catalog import get_catalog
from core.file_ingestion import SUPPORTED, validate_file

router = APIRouter(prefix="/upload", tags=["文件上传"])


async def receive_file(file, project_id, category, business_date, document_number, version_label, source_document_id, replace_document_id=""):
    original = (file.filename or "").replace("\\", "/").split("/")[-1]
    suffix = Path(original).suffix.lower()
    if not original or suffix not in SUPPORTED:
        raise HTTPException(400, "不支持的文件格式")
    catalog = get_catalog()
    try:
        catalog.require_project(project_id)
        if source_document_id:
            catalog.document(source_document_id, project_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    target = settings.UPLOAD_DIR / (uuid.uuid4().hex + suffix)
    size = 0
    try:
        with target.open("wb") as stream:
            while part := await file.read(1024 * 1024):
                size += len(part)
                if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"文件超过 {settings.MAX_UPLOAD_MB}MB，请拆分后上传")
                stream.write(part)
        validate_file(target)
        document, duplicate = catalog.register(target, original, project_id, category, business_date,
                                                document_number, version_label, source_document_id or None, replace_document_id or None)
        if duplicate:
            target.unlink()
        return {"status": document["status"], "document_id": document["id"], "file_id": document["id"],
                "filename": document["original_filename"], "duplicate": duplicate,
                "message": "相同文件与元数据已登记，请查看原任务状态" if duplicate else "原件已接收，处理结果请查看文档台账"}
    except ValueError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.post("/file")
async def upload_file(file: UploadFile = File(...), project_id: str = Form("default"),
                      category: str = Form("general"), business_date: str = Form(""),
                      document_number: str = Form(""), version_label: str = Form(""),
                      source_document_id: str = Form(""), replace_document_id: str = Form("")):
    result = await receive_file(file, project_id, category, business_date, document_number, version_label, source_document_id, replace_document_id)
    return JSONResponse(result, status_code=200 if result["duplicate"] else 202)


@router.post("/batch")
async def upload_batch_files(files: List[UploadFile] = File(...), project_id: str = Form("default"),
                             category: str = Form("general"), business_date: str = Form(""),
                             document_number: str = Form(""), version_label: str = Form("")):
    results = []
    for file in files:
        try:
            results.append(await receive_file(file, project_id, category, business_date, document_number, version_label, ""))
        except HTTPException as exc:
            results.append({"filename": file.filename, "status": "rejected", "message": exc.detail})
    return JSONResponse({"results": results}, status_code=202)
