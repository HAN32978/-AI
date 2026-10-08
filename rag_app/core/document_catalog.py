"""本地文档、完整记录、处理任务和人工整改轨迹。每次操作使用独立 SQLite 连接。"""
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config.settings import settings


def now():
    return datetime.now(timezone.utc).isoformat()


def parse_business_date(value):
    """返回完整日期或月日；没有年份时不猜年份。"""
    value = str(value or "").strip()
    if not value:
        return None, None
    full = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})(?:日|号)?", value)
    short = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]?", value)
    if full:
        year, month, day = map(int, full.groups())
        date = datetime(year, month, day).date()
        return date.isoformat(), date.strftime("%m-%d")
    if short:
        month, day = map(int, short.groups())
        datetime(2000, month, day)  # 包含闰日的月日校验；不填入记录年份。
        return None, f"{month:02d}-{day:02d}"
    raise ValueError("业务日期应为 YYYY-MM-DD 或 X月X日；没有年份时保持未登记年份")


class DocumentCatalog:
    def __init__(self, path=None):
        self.path = Path(path or settings.DOCUMENT_DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL,original_filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,sha256 TEXT NOT NULL,ingest_key TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,business_date TEXT,month_day TEXT,document_number TEXT NOT NULL,
                    version_label TEXT NOT NULL,is_current INTEGER NOT NULL DEFAULT 0,
                    source_document_id TEXT,status TEXT NOT NULL,error TEXT NOT NULL DEFAULT '',
                    chunk_count INTEGER NOT NULL DEFAULT 0,record_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_documents_project ON documents(project_id,is_current,status);
                CREATE TABLE IF NOT EXISTS tasks(
                    id TEXT PRIMARY KEY,document_id TEXT NOT NULL,status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,finished_at TEXT);
                CREATE TABLE IF NOT EXISTS records(
                    id TEXT PRIMARY KEY,document_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,row_number INTEGER NOT NULL,record_number TEXT,
                    business_date TEXT,month_day TEXT,date_raw TEXT,location TEXT,issue_text TEXT,
                    requirement TEXT,responsible_party TEXT,reported_status TEXT,cells_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_records_scope ON records(project_id,month_day,business_date,document_id);
                CREATE TABLE IF NOT EXISTS issues(
                    id TEXT PRIMARY KEY,project_id TEXT NOT NULL,record_id TEXT,description TEXT NOT NULL,
                    location TEXT NOT NULL,responsible_party TEXT NOT NULL,status TEXT NOT NULL,
                    created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS ix_issue_record ON issues(record_id) WHERE record_id IS NOT NULL;
                CREATE TABLE IF NOT EXISTS issue_events(
                    id TEXT PRIMARY KEY,issue_id TEXT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,
                    note TEXT NOT NULL,attachment_ids TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?)", ("default", "默认项目", now()))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at,id")]

    def create_project(self, name):
        name = name.strip()
        if not name:
            raise ValueError("项目名称不能为空")
        project = {"id": uuid.uuid4().hex, "name": name, "created_at": now()}
        with self.connect() as db:
            db.execute("INSERT INTO projects VALUES(:id,:name,:created_at)", project)
        return project

    def require_project(self, project_id):
        with self.connect() as db:
            if not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
                raise ValueError("项目不存在")

    def document(self, document_id, project_id=None):
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row or (project_id and row["project_id"] != project_id):
            raise ValueError("文档不存在或不属于当前项目")
        return dict(row)

    def register(self, path, original_filename, project_id="default", category="general",
                 business_date="", document_number="", version_label="", source_document_id=None):
        self.require_project(project_id)
        date, month_day = parse_business_date(business_date)
        if source_document_id:
            self.document(source_document_id, project_id)
        path = Path(path).resolve()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else self._hash(stream)
        fingerprint = json.dumps([project_id, original_filename, digest, category, date, month_day,
                                  document_number, version_label, source_document_id], ensure_ascii=False)
        key = hashlib.sha256(fingerprint.encode()).hexdigest()
        document_id, task_id, stamp = uuid.uuid4().hex, uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM documents WHERE ingest_key=?", (key,)).fetchone()
            if existing:
                return dict(existing), True
            db.execute("""INSERT INTO documents(id,project_id,original_filename,stored_path,sha256,ingest_key,
                       category,business_date,month_day,document_number,version_label,source_document_id,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (document_id, project_id, original_filename, str(path), digest, key, category, date, month_day,
                        document_number, version_label or stamp, source_document_id, "queued", stamp, stamp))
            db.execute("INSERT INTO tasks(id,document_id,status,attempt,created_at) VALUES(?,?,?,?,?)",
                       (task_id, document_id, "queued", 1, stamp))
        return self.document(document_id), False

    @staticmethod
    def _hash(stream):
        digest = hashlib.sha256()
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
        return digest.hexdigest()

    def retry(self, document_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row:
                raise ValueError("文档不存在")
            if row["status"] not in {"failed", "partial", "stored_only"}:
                raise ValueError("只有失败、部分解析或仅归档的文件可重新处理")
            attempt = db.execute("SELECT MAX(attempt) FROM tasks WHERE document_id=?", (document_id,)).fetchone()[0] or 0
            db.execute("INSERT INTO tasks(id,document_id,status,attempt,created_at) VALUES(?,?,?,?,?)",
                       (uuid.uuid4().hex, document_id, "queued", attempt + 1, now()))
            db.execute("UPDATE documents SET status='queued',error='',updated_at=? WHERE id=?", (now(), document_id))
        return self.document(document_id)

    def recover_tasks(self):
        with self.connect() as db:
            db.execute("UPDATE tasks SET status='queued',error='服务中断后恢复排队' WHERE status IN ('parsing','indexing')")
            db.execute("UPDATE documents SET status='queued' WHERE status IN ('parsing','indexing')")

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            task = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not task:
                return None
            db.execute("UPDATE tasks SET status='parsing' WHERE id=?", (task["id"],))
            db.execute("UPDATE documents SET status='parsing',updated_at=? WHERE id=?", (now(), task["document_id"]))
        return dict(task)

    def set_stage(self, task, status):
        with self.connect() as db:
            db.execute("UPDATE tasks SET status=? WHERE id=?", (status, task["id"]))
            db.execute("UPDATE documents SET status=?,updated_at=? WHERE id=?", (status, now(), task["document_id"]))

    def finish(self, task, status, records=None, chunks=0, error=""):
        document = self.document(task["document_id"])
        with self.connect() as db:
            if records is not None:
                db.execute("DELETE FROM records WHERE document_id=?", (document["id"],))
                for record in records:
                    db.execute("""INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        record["id"], document["id"], document["project_id"], record["sheet_name"], record["row"],
                        record.get("record_number"), record.get("business_date"), record.get("month_day"), record.get("date_raw"),
                        record.get("location"), record.get("issue_text"), record.get("requirement"),
                        record.get("responsible_party"), record.get("reported_status"), json.dumps(record["cells"], ensure_ascii=False)))
            count = db.execute("SELECT COUNT(*) FROM records WHERE document_id=?", (document["id"],)).fetchone()[0]
            db.execute("UPDATE tasks SET status=?,error=?,finished_at=? WHERE id=?", (status, error, now(), task["id"]))
            db.execute("UPDATE documents SET status=?,error=?,chunk_count=?,record_count=?,updated_at=? WHERE id=?",
                       (status, error, chunks, count, now(), document["id"]))
            if status in {"ready", "partial", "stored_only"}:
                newest = db.execute("SELECT id FROM documents WHERE project_id=? AND original_filename=? AND status IN ('ready','partial','stored_only') ORDER BY created_at DESC,id DESC LIMIT 1",
                                    (document["project_id"], document["original_filename"])).fetchone()[0]
                db.execute("UPDATE documents SET is_current=0 WHERE project_id=? AND original_filename=?",
                           (document["project_id"], document["original_filename"]))
                db.execute("UPDATE documents SET is_current=1 WHERE id=?", (newest,))

    def documents(self, project_id="default", current_only=False):
        self.require_project(project_id)
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM documents WHERE project_id=?" + (" AND is_current=1" if current_only else "") + " ORDER BY created_at DESC,id",
                (project_id,))]

    def tasks(self, document_id):
        self.document(document_id)
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM tasks WHERE document_id=? ORDER BY attempt", (document_id,))]

    def query_records(self, project_id="default", document_id=None, date=None, reported_status=None,
                      keyword=None, page=1, page_size=20):
        self.require_project(project_id)
        where = ["r.project_id=?", "d.status IN ('ready','partial')"]
        params = [project_id]
        if document_id:
            self.document(document_id, project_id)
            where.append("r.document_id=?")
            params.append(document_id)
        else:
            where.append("d.is_current=1")
        if date:
            full, short = parse_business_date(date)
            where.append("r.business_date=?" if full else "r.month_day=?")
            params.append(full or short)
        if reported_status == "unknown":
            where.append("(r.reported_status IS NULL OR r.reported_status='')")
        elif reported_status:
            where.append("r.reported_status=?")
            params.append(reported_status)
        if keyword:
            where.append("(instr(COALESCE(r.issue_text,''),?)>0 OR instr(r.cells_json,?)>0)")
            params.extend([keyword, keyword])
        clause = " FROM records r JOIN documents d ON d.id=r.document_id WHERE " + " AND ".join(where)
        with self.connect() as db:
            total = db.execute("SELECT COUNT(*)" + clause, params).fetchone()[0]
            rows = db.execute("SELECT r.*,d.original_filename,d.version_label,d.document_number" + clause +
                              " ORDER BY d.created_at,d.id,r.sheet_name,r.row_number LIMIT ? OFFSET ?",
                              params + [page_size, (page - 1) * page_size]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["cells"] = json.loads(item.pop("cells_json"))
            items.append(item)
        return {"total": total, "page": page, "page_size": page_size, "items": items,
                "note": "没有年份的月日不会自动补年份；未登记的整改状态不等于已整改或未整改。"}

    def record(self, record_id):
        with self.connect() as db:
            row = db.execute("SELECT r.*,d.original_filename,d.version_label FROM records r JOIN documents d ON d.id=r.document_id WHERE r.id=?", (record_id,)).fetchone()
        if not row:
            raise ValueError("记录不存在")
        item = dict(row)
        item["cells"] = json.loads(item.pop("cells_json"))
        return item

    def retrieval_ids(self, project_id="default", document_id=None):
        self.require_project(project_id)
        if document_id:
            doc = self.document(document_id, project_id)
            return [doc["id"]] if doc["status"] in {"ready", "partial"} and doc["chunk_count"] else []
        return [d["id"] for d in self.documents(project_id, True)
                if d["status"] in {"ready", "partial"} and d["chunk_count"]]

    def create_issue(self, project_id, description, actor, location="", responsible_party="", record_id=None):
        self.require_project(project_id)
        if record_id:
            record = self.record(record_id)
            if record["project_id"] != project_id:
                raise ValueError("来源记录不属于当前项目")
            description = description or record.get("issue_text") or ""
            location = location or record.get("location") or ""
        if not description.strip() or not actor.strip():
            raise ValueError("问题描述和登记人不能为空")
        issue_id, stamp = uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if record_id:
                exists = db.execute("SELECT id FROM issues WHERE record_id=?", (record_id,)).fetchone()
                if exists:
                    return self.issue(exists["id"])
            db.execute("INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?,?)", (issue_id, project_id, record_id,
                       description, location, responsible_party, "open", actor, stamp, stamp))
            db.execute("INSERT INTO issue_events VALUES(?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex, issue_id, "created", actor, "登记问题，尚未复查", "[]", stamp))
        return self.issue(issue_id)

    def issue(self, issue_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
            if not row:
                raise ValueError("整改事项不存在")
            result = dict(row)
            result["events"] = [dict(event) for event in db.execute(
                "SELECT * FROM issue_events WHERE issue_id=? ORDER BY created_at,id", (issue_id,))]
        for event in result["events"]:
            event["attachment_ids"] = json.loads(event["attachment_ids"])
        if result["record_id"]:
            result["source_record"] = self.record(result["record_id"])
        return result

    def issues(self, project_id, status=None):
        self.require_project(project_id)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM issues WHERE project_id=?" + (" AND status=?" if status else "") +
                              " ORDER BY created_at DESC,id", [project_id] + ([status] if status else [])).fetchall()
        return [dict(row) for row in rows]

    def add_issue_event(self, issue_id, action, actor, note, attachment_ids=None):
        if not actor.strip() or not note.strip():
            raise ValueError("操作人和处理/复查说明不能为空")
        attachment_ids = attachment_ids or []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            issue = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
            if not issue:
                raise ValueError("整改事项不存在")
            transitions = {
                "reply": ({"open", "reopened", "reply_received"}, "reply_received"),
                "request_recheck": ({"reply_received"}, "recheck_pending"),
                "recheck_pass": ({"recheck_pending"}, "closed"),
                "recheck_fail": ({"recheck_pending"}, "reopened"),
                "reopen": ({"closed"}, "reopened"),
            }
            if action not in transitions or issue["status"] not in transitions[action][0]:
                raise ValueError("当前状态不能执行此操作；需按整改回复、申请复查、人工复查顺序处理")
            for document_id in attachment_ids:
                doc = db.execute("SELECT project_id,stored_path,status FROM documents WHERE id=?", (document_id,)).fetchone()
                if not doc or doc["project_id"] != issue["project_id"]:
                    raise ValueError("附件不属于整改事项所在项目")
                if not Path(doc["stored_path"]).is_file() or doc["status"] not in {"ready", "partial", "stored_only"}:
                    raise ValueError("附件须完成入库或原件归档，且原件文件存在")
            if action in {"reply", "recheck_pass"} and not attachment_ids:
                raise ValueError("整改回复和复查通过须关联至少一份已归档的依据文件")
            stamp = now()
            db.execute("INSERT INTO issue_events VALUES(?,?,?,?,?,?,?)", (uuid.uuid4().hex, issue_id, action,
                       actor.strip(), note.strip(), json.dumps(attachment_ids), stamp))
            db.execute("UPDATE issues SET status=?,updated_at=? WHERE id=?", (transitions[action][1], stamp, issue_id))
        return self.issue(issue_id)


_catalog = None


def get_catalog():
    global _catalog
    if _catalog is None:
        _catalog = DocumentCatalog()
    return _catalog
