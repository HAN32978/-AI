"""完整记录、索引失败恢复、版本范围和人工状态约束回归。"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from core.document_catalog import DocumentCatalog, parse_business_date
from core.file_ingestion import IngestionWorker, read_excel_records, validate_file
from api.routes.qa import QuestionRequest, ask_question


class FakeVectors:
    def __init__(self):
        self.items = {}
    def replace_document(self, document_id, documents):
        self.items[document_id] = documents


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.catalog = DocumentCatalog(self.folder / "catalog.sqlite3")
        self.vectors = FakeVectors()
        self.worker = IngestionWorker(self.catalog, lambda: self.vectors)

    def tearDown(self):
        self.temp.cleanup()

    def workbook(self, name="records.xlsx", count=25):
        path = self.folder / name
        book = Workbook()
        book.active.append(["演示9月9日检查记录"])
        book.active.append(["序号", "部位", "问题描述", "整改要求", "整改状态", "额外原表字段"])
        for i in range(count):
            book.active.append([i + 1, f"测试区{i}", f"演示问题{i}", "清理", "粘贴照片处", f"原值{i}"])
        book.save(path)
        book.close()
        return path

    def register_ready(self, path, **kwargs):
        doc, _ = self.catalog.register(path, path.name, **kwargs)
        self.worker.process_next()
        return self.catalog.document(doc["id"])

    def test_full_rows_keep_unknown_year_and_status(self):
        self.register_ready(self.workbook())
        data = self.catalog.query_records(date="9月9日", page_size=10)
        self.assertEqual(data["total"], 25)
        self.assertEqual(len(data["items"]), 10)
        self.assertIsNone(data["items"][0]["business_date"])
        self.assertIsNone(data["items"][0]["reported_status"])
        self.assertEqual(data["items"][0]["cells"]["额外原表字段"], "原值0")
        self.assertEqual(self.catalog.query_records(date="2026-09-09")["total"], 0)

    def test_supplied_year_is_used_without_overwriting_conflicting_row_date(self):
        doc = self.register_ready(self.workbook(), business_date="2026-09-09")
        self.assertEqual(self.catalog.query_records(date="2026-09-09")["total"], 25)
        self.assertEqual(doc["record_count"], 25)

    def test_index_failure_preserves_sql_rows_retry_no_duplicates(self):
        doc, _ = self.catalog.register(self.workbook(), "records.xlsx")
        with patch.object(self.vectors, "replace_document", side_effect=RuntimeError("模拟索引离线")):
            self.worker.process_next()
        self.assertEqual(self.catalog.document(doc["id"])["status"], "partial")
        self.assertEqual(self.catalog.query_records()["total"], 25)
        self.catalog.retry(doc["id"])
        self.worker.process_next()
        self.assertEqual(self.catalog.query_records()["total"], 25)
        self.assertEqual(len(self.vectors.items[doc["id"]]), 25)
        self.assertEqual(len(self.catalog.tasks(doc["id"])), 2)

    def test_identical_upload_is_deduplicated(self):
        path = self.workbook()
        one, _ = self.catalog.register(path, path.name)
        two, duplicate = self.catalog.register(path, path.name)
        self.assertTrue(duplicate)
        self.assertEqual(one["id"], two["id"])
        self.assertEqual(len(self.catalog.tasks(one["id"])), 1)

    def test_versions_and_project_do_not_mix(self):
        one = self.register_ready(self.workbook(count=25), version_label="v1")
        two = self.register_ready(self.workbook(count=2), version_label="v2")
        project = self.catalog.create_project("其他项目")
        self.register_ready(self.workbook("other.xlsx", 3), project_id=project["id"])
        self.assertEqual(self.catalog.query_records()["total"], 2)
        self.assertEqual(self.catalog.query_records(document_id=one["id"])["total"], 25)
        with self.assertRaises(ValueError):
            self.catalog.query_records(project["id"], two["id"])
        self.assertEqual(self.catalog.retrieval_ids(), [two["id"]])

    def test_old_retry_does_not_replace_new_current_version(self):
        old = self.register_ready(self.workbook(count=1), version_label="v1")
        new = self.register_ready(self.workbook(count=2), version_label="v2")
        task = {"id": self.catalog.tasks(old["id"])[0]["id"], "document_id": old["id"]}
        self.catalog.finish(task, "partial", error="旧版重新处理")
        self.assertFalse(self.catalog.document(old["id"])["is_current"])
        self.assertTrue(self.catalog.document(new["id"])["is_current"])

    def test_restart_recovers_claimed_task(self):
        doc, _ = self.catalog.register(self.workbook(count=1), "records.xlsx")
        self.catalog.claim()
        self.catalog = DocumentCatalog(self.folder / "catalog.sqlite3")
        self.catalog.recover_tasks()
        IngestionWorker(self.catalog, lambda: self.vectors).process_next()
        self.assertEqual(self.catalog.document(doc["id"])["status"], "ready")

    def test_record_query_never_calls_llm(self):
        self.register_ready(self.workbook())
        with patch("api.routes.qa.get_catalog", return_value=self.catalog), patch("api.dependencies.get_rag_chain", side_effect=AssertionError("不应调用模型")):
            from api.dependencies import LazyRAGChain
            result = asyncio.run(ask_question(QuestionRequest(question="查询9月9日全部检查问题", page_size=10), LazyRAGChain()))
        self.assertEqual(result.total, 25)
        self.assertEqual(len(result.records), 10)

    def test_manual_closure_requires_sequence_actor_note_evidence(self):
        evidence = self.folder / "reply.txt"
        evidence.write_text("演示整改依据", encoding="utf-8")
        doc = self.register_ready(evidence)
        issue = self.catalog.create_issue("default", "演示现场问题", "登记人")
        with self.assertRaises(ValueError):
            self.catalog.add_issue_event(issue["id"], "recheck_pass", "复查人", "通过", [doc["id"]])
        with self.assertRaises(ValueError):
            self.catalog.add_issue_event(issue["id"], "reply", "整改人", "已提交", [])
        self.catalog.add_issue_event(issue["id"], "reply", "整改人", "演示回复", [doc["id"]])
        self.catalog.add_issue_event(issue["id"], "request_recheck", "申请人", "申请复查")
        result = self.catalog.add_issue_event(issue["id"], "recheck_pass", "复查人", "人工核实通过", [doc["id"]])
        self.assertEqual(result["status"], "closed")
        self.assertEqual(len(result["events"]), 4)
        self.assertEqual(DocumentCatalog(self.catalog.path).issue(issue["id"])["status"], "closed")

    def test_cross_project_evidence_and_missing_file_are_rejected(self):
        project = self.catalog.create_project("其他项目")
        path = self.folder / "reply.txt"
        path.write_text("演示依据", encoding="utf-8")
        other = self.register_ready(path, project_id=project["id"])
        issue = self.catalog.create_issue("default", "问题", "登记人")
        with self.assertRaises(ValueError):
            self.catalog.add_issue_event(issue["id"], "reply", "整改人", "回复", [other["id"]])
        own = self.register_ready(path)
        path.unlink()
        with self.assertRaises(ValueError):
            self.catalog.add_issue_event(issue["id"], "reply", "整改人", "回复", [own["id"]])

    def test_wrong_file_header_rejected(self):
        path = self.folder / "fake.dwg"
        path.write_text("并非 DWG", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_file(path)

    def test_filename_date_and_invalid_date(self):
        path = self.workbook(count=1)
        rows = read_excel_records(path, "test", original_filename="9月9日记录.xlsx")
        self.assertEqual(rows[0]["month_day"], "09-09")
        self.assertEqual(parse_business_date("9月9日"), (None, "09-09"))
        with self.assertRaises(ValueError):
            parse_business_date("2026-02-30")


if __name__ == "__main__":
    unittest.main()
