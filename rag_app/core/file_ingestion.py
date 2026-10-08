"""可恢复的单进程入库 Worker。原件、完整 Excel 记录和语义索引分别保存。"""
import logging
import re
import threading
import uuid
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import settings
from core.document_catalog import get_catalog, parse_business_date

logger = logging.getLogger(__name__)
SUPPORTED = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls",
             ".dwg", ".dxf", ".rvt", ".ifc", ".png", ".jpg", ".jpeg"}
STORED_ONLY = {
    ".dwg": "原件已归档。当前版本不直接解析 DWG；请提供对应 DXF/PDF，可关联原件。",
    ".rvt": "原件已归档。请通过 Revit 导出 IFC/PDF 后上传，并关联此 RVT 原件。",
    ".ifc": "IFC 原件已归档。本阶段尚未启用 BIM 属性解析，内容暂不可检索。",
    ".doc": "旧版 DOC 原件已归档。请另存为 DOCX/PDF 后上传。",
    ".png": "现场图片已归档，可关联整改事项；当前不自动识别照片或判断整改完成。",
    ".jpg": "现场图片已归档，可关联整改事项；当前不自动识别照片或判断整改完成。",
    ".jpeg": "现场图片已归档，可关联整改事项；当前不自动识别照片或判断整改完成。",
}


def validate_file(path):
    """基本类型头验证，不能据此保证 CAD/BIM 原件结构完整。"""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError("不支持的文件类型")
    if path.stat().st_size == 0:
        raise ValueError("不能上传空文件")
    with path.open("rb") as stream:
        head = stream.read(4096)
    expected = {
        ".pdf": head.lstrip().startswith(b"%PDF-"),
        ".dwg": bool(re.match(rb"AC\d{4}", head)),
        ".rvt": head.startswith(bytes.fromhex("d0cf11e0a1b11ae1")),
        ".doc": head.startswith(bytes.fromhex("d0cf11e0a1b11ae1")),
        ".xls": head.startswith(bytes.fromhex("d0cf11e0a1b11ae1")),
        ".ifc": b"ISO-10303-21" in head,
        ".dxf": head.startswith(b"AutoCAD Binary DXF") or (b"SECTION" in head and b"0" in head),
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": head.startswith(b"\xff\xd8\xff"),
        ".jpeg": head.startswith(b"\xff\xd8\xff"),
    }
    if ext in expected and not expected[ext]:
        raise ValueError("文件内容与扩展名不匹配，或文件头已损坏")
    if ext in {".docx", ".xlsx"}:
        required = "word/document.xml" if ext == ".docx" else "xl/workbook.xml"
        try:
            with ZipFile(path) as zipped:
                if required not in zipped.namelist():
                    raise ValueError("Office 文件缺少必要结构")
                if sum(item.file_size for item in zipped.infolist()) > 250 * 1024 * 1024:
                    raise ValueError("Office 文件解压后过大，请拆分文件")
        except BadZipFile as exc:
            raise ValueError("Office 文件已损坏") from exc


ALIASES = {
    "record_number": ["序号", "编号", "记录编号"],
    "date_raw": ["检查日期", "验收日期", "业务日期", "日期", "检查时间"],
    "location": ["检查部位", "整改部位", "部位", "位置", "区域"],
    "issue_text": ["整改问题描述", "问题描述", "检查问题", "发现问题", "问题", "隐患描述"],
    "requirement": ["整改要求", "处理要求", "整改措施", "整改建议"],
    "responsible_party": ["责任单位", "责任人", "责任方", "整改责任人"],
    "reported_status": ["整改状态", "处理状态", "状态", "销项状态"],
}


def canonical_header(value):
    return re.sub(r"\s+", "", str(value or ""))


def read_excel_records(path, document_id, context_date=None, original_filename=None):
    import pandas as pd
    path = Path(path)
    records = []
    headers_known = {name for group in ALIASES.values() for name in group}
    with pd.ExcelFile(path, engine="openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd") as workbook:
        for sheet_name in workbook.sheet_names:
            table = pd.read_excel(workbook, sheet_name=sheet_name, header=None, dtype=str, keep_default_na=False).fillna("")
            table = table.loc[table.apply(lambda row: any(str(v).strip() for v in row), axis=1)]
            if table.empty:
                continue
            candidates = list(table.head(20).iterrows())
            scored = [(sum(canonical_header(v) in headers_known for v in row), index) for index, row in candidates]
            best_score = max(score for score, _ in scored)
            header_index = next(index for score, index in scored if score == best_score) if best_score >= 2 else next(
                (index for index, row in candidates if sum(bool(str(v).strip()) for v in row) >= 2), table.index[0])
            header = [canonical_header(v) or f"列{col + 1}" for col, v in enumerate(table.loc[header_index])]
            # 重复列名保存为独立列，不吞掉第二个单元格。
            seen = {}
            unique = []
            for name in header:
                seen[name] = seen.get(name, 0) + 1
                unique.append(name if seen[name] == 1 else f"{name}#{seen[name]}")
            title = "；".join(str(v).strip() for _, row in table.loc[table.index < header_index].iterrows()
                             for v in row if str(v).strip())
            title_date = re.search(r"(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]", title + " " + sheet_name + " " + (original_filename or path.name))
            for index, row in table.loc[table.index > header_index].iterrows():
                cells = {name: str(v).strip() for name, v in zip(unique, row)}
                record = {field: next((cells[name] for name in aliases if cells.get(name)), None)
                          for field, aliases in ALIASES.items()}
                if all(not value for value in cells.values()) or all(cells.get(name) == name for name in header):
                    continue
                raw = record["date_raw"] or context_date or (title_date.group() if title_date else "")
                try:
                    date, month_day = parse_business_date(raw)
                except ValueError:
                    date, month_day = None, None
                if not date and month_day and context_date:
                    explicit_date, explicit_md = parse_business_date(context_date)
                    if explicit_date and explicit_md == month_day:
                        date = explicit_date
                if record["reported_status"] in {"粘贴照片处", "图片占位", "照片占位", "待补充", "照片"}:
                    record["reported_status"] = None
                record.update({"id": f"{document_id}:{sheet_name}:{int(index) + 1}", "sheet_name": sheet_name,
                               "row": int(index) + 1, "cells": cells, "business_date": date,
                               "month_day": month_day, "date_raw": str(raw), "title": title})
                records.append(record)
                if len(records) > 20000:
                    raise ValueError("表格记录超过 20000 行，请按项目或日期拆分")
    return records


def parse_document(document):
    from core.document_loader import DocumentLoader
    path = Path(document["stored_path"])
    ext = path.suffix.lower()
    validate_file(path)
    if ext in STORED_ONLY:
        return [], [], STORED_ONLY[ext], "stored_only"
    records, warning = [], ""
    if ext in {".xlsx", ".xls"}:
        context = document.get("business_date")
        if not context and document.get("month_day"):
            month, day = document["month_day"].split("-")
            context = f"{int(month)}月{int(day)}日"
        records = read_excel_records(path, document["id"], context, document["original_filename"])
        documents = [Document(page_content=f"工作表：{r['sheet_name']}\n标题：{r['title']}\nExcel 行号：{r['row']}\n" +
                    "；".join(f"{name}：{value}" for name, value in r["cells"].items() if value),
                    metadata={"sheet_name": r["sheet_name"], "row": r["row"]}) for r in records]
    elif ext == ".dxf":
        try:
            import ezdxf
        except ImportError:
            return [], [], "DXF 原件已归档，未安装文字解析组件；可提供对应 PDF。", "stored_only"
        drawing = ezdxf.readfile(path)
        documents = []
        for layout in drawing.layouts:
            for entity in layout:
                entities = list(entity.attribs) if entity.dxftype() == "INSERT" else [entity]
                for item in entities:
                    kind = item.dxftype()
                    text = item.plain_text() if kind == "MTEXT" else item.dxf.text if kind in {"TEXT", "ATTRIB"} else ""
                    if text.strip():
                        documents.append(Document(page_content=text, metadata={"layout": layout.name,
                                                               "entity_handle": item.dxf.handle, "layer": item.dxf.layer}))
        warning = "仅提取直接可读取的文字与块属性；外参、代理对象和嵌套块内容未保证完整，不进行几何审查。"
    elif ext in {".txt", ".md"}:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("gb18030")
        documents = [Document(page_content=text)]
    else:
        documents = DocumentLoader.LOADER_MAP[ext](str(path)).load()
    documents = [doc for doc in documents if doc.page_content.strip()]
    if not documents:
        return [], records, "原件已归档，未提取到有效文字。本阶段不包含扫描件 OCR。", "stored_only"
    metadata = {key: document[key] for key in ["project_id", "original_filename", "category", "version_label"]}
    metadata.update({"document_id": document["id"], "source": str(path), "file_name": document["original_filename"]})
    for doc in documents:
        doc.metadata.update(metadata)
    splitter = RecursiveCharacterTextSplitter(chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP,
                                               separators=["\n\n", "\n", "。", "；", " ", ""])
    return splitter.split_documents(documents), records, warning, "partial" if warning else "ready"


class IngestionWorker:
    def __init__(self, catalog=None, vector_factory=None):
        self.catalog = catalog or get_catalog()
        self.vector_factory = vector_factory
        self.stop_event = threading.Event()
        self.thread = None

    def process_next(self):
        task = self.catalog.claim()
        if not task:
            return False
        records = None
        try:
            document = self.catalog.document(task["document_id"])
            docs, records, warning, status = parse_document(document)
            if docs:
                self.catalog.set_stage(task, "indexing")
                if self.vector_factory is None:
                    from core.vector_store import get_vector_store_manager
                    store = get_vector_store_manager()
                else:
                    store = self.vector_factory()
                store.replace_document(document["id"], docs)
            self.catalog.finish(task, status, records=records, chunks=len(docs), error=warning)
        except Exception as exc:
            logger.exception("文件处理失败，文档 ID=%s", task["document_id"])
            # 表格解析与语义索引分别交付；索引服务失败不抹掉完整原表记录。
            self.catalog.finish(task, "partial" if records else "failed", records=records,
                                error=f"{'完整表格记录已保存，语义索引失败：' if records else ''}{type(exc).__name__}: {str(exc)[:500]}")
        return True

    def import_existing(self):
        count = 0
        with self.catalog.connect() as db:
            known = {str(Path(row[0]).resolve()) for row in db.execute("SELECT stored_path FROM documents")}
        for path in sorted(settings.UPLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime):
            if path.is_file() and path.suffix.lower() in SUPPORTED and str(path.resolve()) not in known:
                name = re.sub(r"^[0-9a-f]{8}_", "", path.name)
                try:
                    _, duplicate = self.catalog.register(path, name)
                    count += not duplicate
                except Exception:
                    logger.exception("历史文件登记失败")
        return count

    def start(self):
        self.catalog.recover_tasks()
        self.import_existing()
        def run():
            while not self.stop_event.is_set():
                if not self.process_next():
                    self.stop_event.wait(0.3)
        self.thread = threading.Thread(target=run, name="document-ingestion", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
