import json
import subprocess
import tempfile
import types
from pathlib import Path
from openpyxl import Workbook

repo = Path(__file__).resolve().parents[1]
(repo / ".runtime").mkdir(exist_ok=True)
ref = "51f55af42cba3fe345eb887a546689029b414004"
def old_module(relative, name):
    text = subprocess.check_output(["git", "show", f"{ref}:{relative}"], cwd=repo).decode()
    module = types.ModuleType(name)
    exec(compile(text, relative, "exec"), module.__dict__)
    return module
catalog_module = old_module("rag_app/core/document_catalog.py", "previous_catalog")
ingestion = old_module("rag_app/core/file_ingestion.py", "previous_ingestion")
ingestion.parse_business_date = catalog_module.parse_business_date
class Store:
    def replace_document(self, *args):
        pass
with tempfile.TemporaryDirectory(dir=repo / '.runtime') as folder:
    base = Path(folder)
    catalog = catalog_module.DocumentCatalog(base / "previous.sqlite3")
    worker = ingestion.IngestionWorker(catalog, lambda: Store())
    def register(name, rows, original):
        path = base / name
        book = Workbook()
        book.active.append(["日期", "问题描述", "整改状态"])
        for row in rows:
            book.active.append(row)
        book.save(path)
        book.close()
        document, _ = catalog.register(path, original)
        worker.process_next()
        return catalog.document(document["id"])
    register("day9.xlsx", [["9月9日", "演示9日问题", ""]], "检查记录.xlsx")
    register("day10.xlsx", [["9月10日", "演示10日问题", ""]], "检查记录.xlsx")
    day9 = catalog.query_records(date="9月9日")["total"]
    day10 = catalog.query_records(date="9月10日")["total"]
    values = ["9月9日", "9.9", "9/9", "09-09", "九月九日", "二〇二六年九月九日", "2026-09-09 00:00:00", "2026年9月", "无法辨认"]
    irregular = register("irregular.xlsx", [[v, "演示问题", ""] for v in values], "不规整.xlsx")
    matches = catalog.query_records(document_id=irregular["id"], date="9月9日")
    summary = register("summary.xlsx", [["9月9日", "演示问题", ""], ["合计", "1", ""]], "汇总行.xlsx")
    status = register("status.xlsx", [["9月9日", "演示问题", "粘贴照片处。"]], "状态.xlsx")
    reported = catalog.query_records(document_id=status["id"])["items"][0]["reported_status"]
    result = {"baseline_commit": ref, "scope": "隔离合成 Excel 与真实 SQLite；执行从 Git 读取的上一版源码，向量写入使用替身；不验证旧版模型与页面。",
              "same_filename": {"day9_matching": day9, "day10_matching": day10},
              "irregular_dates": {"retained_rows": irregular["record_count"], "day9_matching": matches["total"], "warning_count_exposed": "unresolved_date_count" in matches},
              "summary": {"source_problem_rows": 1, "stored_rows": summary["record_count"]},
              "placeholder": {"source_status": reported, "stored_as_real_status": bool(reported)}}
    assert (day9, day10) == (0, 1)
    assert matches["total"] == 2 and summary["record_count"] == 2 and reported
    (repo / "docs/上一版缺陷复现_2026-10-08.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
