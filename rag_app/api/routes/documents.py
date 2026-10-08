"""项目、文档台账、完整记录、原件下载与人工整改事件。"""
import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from core.document_catalog import get_catalog

router = APIRouter(tags=["文档台账与现场整改"])


def checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "记录已登记或状态已变化，请刷新后重试") from exc


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.get("/projects")
def projects():
    return {"items": get_catalog().projects()}


@router.post("/projects", status_code=201)
def create_project(request: ProjectCreate):
    return checked(get_catalog().create_project, request.name)


@router.get("/documents/stats")
def stats(project_id: str = "default"):
    docs = checked(get_catalog().documents, project_id)
    states = {}
    for doc in docs:
        states[doc["status"]] = states.get(doc["status"], 0) + 1
    current = [doc for doc in docs if doc["is_current"]]
    return {"document_count": len(docs), "current_document_count": len(current), "states": states,
            "record_count": sum(doc["record_count"] for doc in current if doc["status"] in {"ready", "partial"}),
            "indexed_chunks": sum(doc["chunk_count"] for doc in current if doc["status"] in {"ready", "partial"})}


@router.get("/documents")
def documents(project_id: str = "default", current_only: bool = False):
    return {"items": checked(get_catalog().documents, project_id, current_only)}


@router.get("/documents/{document_id}")
def document(document_id: str, project_id: str = "default"):
    catalog = get_catalog()
    item = checked(catalog.document, document_id, project_id)
    item["tasks"] = catalog.tasks(document_id)
    return item


@router.post("/documents/{document_id}/retry", status_code=202)
def retry(document_id: str, project_id: str = "default"):
    checked(get_catalog().document, document_id, project_id)
    return checked(get_catalog().retry, document_id)


@router.get("/documents/{document_id}/download")
def download(document_id: str, project_id: str = "default"):
    item = checked(get_catalog().document, document_id, project_id)
    if not Path(item["stored_path"]).is_file():
        raise HTTPException(404, "原件已不在归档目录")
    return FileResponse(item["stored_path"], filename=item["original_filename"])


@router.get("/records")
def records(project_id: str = "default", document_id: str | None = None, date: str | None = None,
            reported_status: str | None = None, keyword: str | None = None,
            page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)):
    return checked(get_catalog().query_records, project_id, document_id, date, reported_status, keyword, page, page_size)


@router.get("/records/export")
def export_records(project_id: str = "default", document_id: str | None = None,
                   date: str | None = None, reported_status: str | None = None, keyword: str | None = None):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["文件", "版本", "业务日期", "部位", "问题原文", "整改要求", "原表状态", "工作表", "行号", "责任方", "记录ID", "原表全部字段JSON"])
    page = 1
    while True:
        result = checked(get_catalog().query_records, project_id, document_id, date, reported_status, keyword, page, 200)
        for record in result["items"]:
            values = [record["original_filename"], record["version_label"], record["business_date"] or record["date_raw"],
                      record["location"], record["issue_text"], record["requirement"], record["reported_status"], record["sheet_name"], record["row_number"],
                      record["responsible_party"], record["id"], json.dumps(record["cells"], ensure_ascii=False)]
            writer.writerow(["'" + str(v) if str(v or "").startswith(("=", "+", "-", "@")) else v or "" for v in values])
        if page * 200 >= result["total"]:
            break
        page += 1
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="records.csv"'})


class IssueCreate(BaseModel):
    project_id: str = "default"
    record_id: str | None = None
    description: str = Field("", max_length=5000)
    actor: str = Field(min_length=1, max_length=100)
    location: str = Field("", max_length=500)
    responsible_party: str = Field("", max_length=200)


class IssueEvent(BaseModel):
    project_id: str = "default"
    action: Literal["reply", "request_recheck", "recheck_pass", "recheck_fail", "reopen"]
    actor: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=5000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)


@router.get("/issues")
def issues(project_id: str = "default", status: str | None = None):
    return {"items": checked(get_catalog().issues, project_id, status)}


@router.post("/issues", status_code=201)
def create_issue(request: IssueCreate):
    return checked(get_catalog().create_issue, request.project_id, request.description, request.actor,
                   request.location, request.responsible_party, request.record_id)


@router.get("/issues/{issue_id}")
def issue(issue_id: str, project_id: str = "default"):
    result = checked(get_catalog().issue, issue_id)
    if result["project_id"] != project_id:
        raise HTTPException(422, "整改事项不属于当前项目")
    return result


@router.post("/issues/{issue_id}/events")
def event(issue_id: str, request: IssueEvent):
    issue(issue_id, request.project_id)
    return checked(get_catalog().add_issue_event, issue_id, request.action, request.actor,
                   request.note, request.attachment_ids)
