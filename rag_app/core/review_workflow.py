"""Connect CAD audit findings to RAG evidence without claiming an automatic verdict."""

from typing import Any, Callable


def build_query(issue: dict[str, Any]) -> str:
    fields = (
        "professional", "checkpoint_name", "description", "standard_code", "standard_clause"
    )
    return " ".join(str(issue.get(key, "")).strip() for key in fields if issue.get(key)).strip()


def review_issues(
    issues: list[dict[str, Any]],
    retrieve: Callable[[str, int], list[Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return review packets; retrieved chunks are candidates, never verified clauses."""
    packets = []
    for index, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            raise ValueError(f"第 {index} 条审查问题必须是对象")
        description = str(issue.get("description", "")).strip()
        if not description:
            raise ValueError(f"第 {index} 条审查问题缺少 description")
        query = build_query(issue)
        documents = retrieve(query, top_k)
        sources = []
        for doc in documents:
            metadata = getattr(doc, "metadata", {}) or {}
            sources.append({
                "source": str(metadata.get("original_filename") or metadata.get("file_name") or metadata.get("source") or "未知资料"),
                "page": metadata.get("page"),
                "content": str(getattr(doc, "page_content", ""))[:600],
            })
        severity = str(issue.get("severity") or "").upper()
        status = "待补充依据" if not sources else ("高风险人工复核" if severity == "A" else "人工复核")
        packets.append({
            "issue_id": str(issue.get("issue_id") or f"ISSUE-{index:03d}"),
            "professional": str(issue.get("professional") or issue.get("discipline") or ""),
            "drawing_name": str(issue.get("drawing_name") or ""),
            "location": str(issue.get("location") or ""),
            "description": description,
            "severity": severity,
            "standard_code_from_audit": str(issue.get("standard_code") or ""),
            "standard_clause_from_audit": str(issue.get("standard_clause") or ""),
            "retrieval_query": query,
            "candidate_sources": sources,
            "status": status,
            "review_note": "审图输出与检索片段均须核对图纸、规范版本和条款；本流程不自动判定合规。",
        })
    return packets
