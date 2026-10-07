"""Contract checks between the upstream CAD issue schema and the RAG API."""

from types import SimpleNamespace
from unittest import TestCase

from fastapi import HTTPException

from api.routes.review import ReviewRequest, match_review_evidence


class FakeStore:
    def similarity_search(self, query, k):
        if "疏散门" not in query:
            return []
        return [SimpleNamespace(
            metadata={"original_filename": "演示规范.pdf", "page": 2},
            page_content="演示片段：须结合有效规范版本和图纸核查。",
        )][:k]


class ReviewWorkflowTests(TestCase):
    def test_cad_issue_to_review_packet(self):
        result = match_review_evidence(ReviewRequest(**{
            "project_name": "示例项目",
            "issues": [
                {"issue_id": "DEMO-001", "description": "疏散门宽度待核查", "severity": "A", "drawing_name": "建施-01.dxf"},
                {"issue_id": "DEMO-002", "description": "楼梯尺寸待核查", "severity": "B"},
            ],
        }), store=FakeStore())
        self.assertEqual(result["summary"], {"total": 2, "missing_sources": 1, "high_risk": 1})
        self.assertEqual(result["issues"][0]["status"], "高风险人工复核")
        self.assertEqual(result["issues"][0]["candidate_sources"][0]["source"], "演示规范.pdf")
        self.assertEqual(result["issues"][1]["status"], "待补充依据")


    def test_issue_without_description_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            match_review_evidence(ReviewRequest(issues=[{"issue_id": "X"}]), store=FakeStore())
        self.assertEqual(caught.exception.status_code, 422)
