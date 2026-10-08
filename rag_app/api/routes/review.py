"""CAD finding -> knowledge retrieval -> human review workflow."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.review_workflow import review_issues
from core.vector_store import get_vector_store_manager


router = APIRouter(prefix="/review", tags=["图纸审查与资料检索"])


class ReviewRequest(BaseModel):
    project_name: str = Field(default="演示项目", max_length=100)
    issues: list[dict] = Field(min_length=1, max_length=50)
    top_k: int = Field(default=3, ge=1, le=10)


def get_review_store():
    return get_vector_store_manager()


@router.post("/evidence")
def match_review_evidence(request: ReviewRequest, store=Depends(get_review_store)):
    """Accept upstream ProblemPool JSON's issues list and find candidate sources."""
    try:
        packets = review_issues(
            request.issues,
            lambda query, top_k: store.similarity_search(query, k=top_k),
            request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "project_name": request.project_name,
        "workflow": ["审图问题导入", "工程资料检索", "候选依据展示", "人工复核"],
        "issues": packets,
        "summary": {
            "total": len(packets),
            "missing_sources": sum(not packet["candidate_sources"] for packet in packets),
            "high_risk": sum(packet["severity"] == "A" for packet in packets),
        },
    }
