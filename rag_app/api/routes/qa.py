"""语义问答与不受 top-k 截断的结构化记录查询。"""
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from api.dependencies import get_rag_chain_dep, LazyRAGChain
from core.document_catalog import get_catalog
from core.memory_manager import get_memory_manager
from core.llm_client import LLMServiceError

router = APIRouter(prefix="/qa", tags=["智能问答"])


class QuestionRequest(BaseModel):
    question: str = Field(max_length=5000)
    session_id: str = "default"
    project_id: str = "default"
    document_id: str | None = None
    business_date: str | None = None
    query_mode: Literal["auto", "records", "semantic"] = "auto"
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)


class SourceInfo(BaseModel):
    source: str
    page: int | None = None
    sheet_name: str | None = None
    row: int | None = None
    document_id: str | None = None
    version_label: str | None = None
    layout: str | None = None
    entity_handle: str | None = None
    content: str


class AnswerResponse(BaseModel):
    answer: str
    sources: list
    intent: str
    records: list = Field(default_factory=list)
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


def scope_session(project_id, document_id, session_id):
    import json
    return json.dumps([project_id, document_id, session_id], ensure_ascii=False)


@router.post("/ask", response_model=AnswerResponse)
async def ask_question(request: QuestionRequest, rag_chain=Depends(get_rag_chain_dep)):
    question = request.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    catalog = get_catalog()
    try:
        catalog.require_project(request.project_id)
        if request.document_id:
            catalog.document(request.document_id, request.project_id)
        date_match = re.search(r"\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}(?:日|号)?|\d{1,2}月\d{1,2}[日号]?", question)
        date = request.business_date or (date_match.group() if date_match else None)
        structured = request.query_mode == "records" or (request.query_mode == "auto" and
                     bool(date) and any(term in question for term in ["记录", "问题", "检查", "全部", "清单"]))
        session = scope_session(request.project_id, request.document_id, request.session_id)
        if structured:
            # 闭环状态必须来自人工事件，不能用原表空白/照片占位推断。
            if any(term in question for term in ["未销项", "已销项", "已整改", "未整改"]):
                return AnswerResponse(answer="原表状态与人工闭环状态分别保存。请在记录查询中筛选原表状态，或在现场整改中查看人工复查与销项记录；当前问题未自动推断整改完成情况。", sources=[], intent="需明确状态口径")
            data = catalog.query_records(request.project_id, request.document_id, date=date,
                                         page=request.page, page_size=request.page_size)
            rows = data["items"]
            answer = f"按当前项目、文档和日期筛选，共 {data['total']} 条记录；第 {data['page']} 页显示 {len(rows)} 条。\n\n"
            for i, row in enumerate(rows, start=(request.page - 1) * request.page_size + 1):
                answer += f"{i}. {row.get('location') or '部位未登记'}：{row.get('issue_text') or '见原表字段'}；要求：{row.get('requirement') or '未登记'}；原表状态：{row.get('reported_status') or '未登记'}\n"
            answer += "\n" + data["note"] + "完整清单和原表字段可在记录查询页面查看及导出。"
            sources = [{"source": row["original_filename"], "sheet_name": row["sheet_name"],
                        "row": row["row_number"], "document_id": row["document_id"], "version_label": row["version_label"],
                        "content": "；".join(f"{k}：{v}" for k, v in row["cells"].items() if v)} for row in rows]
            get_memory_manager().add_exchange(session, question, answer)
            return AnswerResponse(answer=answer, sources=sources, intent="完整记录查询", records=rows,
                                  total=data["total"], page=data["page"], page_size=data["page_size"])
        ids = catalog.retrieval_ids(request.project_id, request.document_id)
        if isinstance(rag_chain, LazyRAGChain):
            result = rag_chain.ask(question, session, document_ids=ids)
        else:  # 保留课程的依赖替换测试接口。
            result = rag_chain.ask(question, session)
        return AnswerResponse(answer=result["answer"], sources=[SourceInfo(**s) for s in result["sources"]], intent=result["intent"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/clear_memory")
async def clear_conversation_memory(session_id: str = Query("default"), project_id: str = "default",
                                    document_id: str | None = None, rag_chain=Depends(get_rag_chain_dep)):
    rag_chain.clear_session(scope_session(project_id, document_id, session_id))
    return {"status": "success", "message": "对话记忆已清除"}


@router.get("/history")
async def get_chat_history(session_id: str = Query("default"), project_id: str = "default",
                           document_id: str | None = None, rag_chain=Depends(get_rag_chain_dep)):
    return {"history": rag_chain.get_chat_history(scope_session(project_id, document_id, session_id))}
