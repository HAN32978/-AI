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
from core.date_parser import parse_business_date


def now():
    return datetime.now(timezone.utc).isoformat()


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
            self._migrate(db)

    @staticmethod
    def _migrate(db):
        additions = {"documents": {"version_group": "TEXT NOT NULL DEFAULT ''", "parse_report": "TEXT NOT NULL DEFAULT '{}'"},
                     "records": {"date_quality": "TEXT NOT NULL DEFAULT 'unverified'", "date_error": "TEXT NOT NULL DEFAULT ''"},
                     "issue_events": {"evidence_date": "TEXT NOT NULL DEFAULT ''"}}
        for table, columns in additions.items():
            existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns.items():
                if name not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        # 旧版没有记录替换意图，保守恢复为独立文档，避免同名不同业务记录继续隐藏。
        db.execute("UPDATE documents SET version_group=id,is_current=CASE WHEN status IN ('ready','partial','stored_only') THEN 1 ELSE is_current END WHERE version_group=''")
        db.execute("UPDATE records SET date_quality=CASE WHEN business_date IS NOT NULL THEN 'full' WHEN month_day IS NOT NULL THEN 'month_day' WHEN COALESCE(date_raw,'')='' THEN 'missing' ELSE 'unrecognized' END WHERE date_quality='unverified'")
        legacy = db.execute("SELECT id,stored_path FROM documents WHERE parse_report='{}' AND status IN ('ready','partial')").fetchall()
        for document in legacy:
            if Path(document["stored_path"]).suffix.lower() not in {".xlsx", ".xls"}:
                continue
            attempt = db.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM tasks WHERE document_id=?", (document["id"],)).fetchone()[0]
            db.execute("INSERT INTO tasks(id,document_id,status,attempt,error,created_at) VALUES(?,?,?,?,?,?)",
                       (uuid.uuid4().hex, document["id"], "queued", attempt, "解析规则升级后重新核对表格", now()))
            db.execute("UPDATE documents SET status='queued',error='解析规则升级后重新核对表格' WHERE id=?", (document["id"],))

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
                 business_date="", document_number="", version_label="", source_document_id=None, replace_document_id=None):
        self.require_project(project_id)
        date, month_day = parse_business_date(business_date)
        if source_document_id:
            self.document(source_document_id, project_id)
        replacement = self.document(replace_document_id, project_id) if replace_document_id else None
        path = Path(path).resolve()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else self._hash(stream)
        metadata = [project_id, original_filename, digest, category, date, month_day, document_number, version_label, source_document_id]
        if replacement:
            metadata.append(replacement["version_group"])
        fingerprint = json.dumps(metadata, ensure_ascii=False)
        key = hashlib.sha256(fingerprint.encode()).hexdigest()
        document_id, task_id, stamp = uuid.uuid4().hex, uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM documents WHERE ingest_key=?", (key,)).fetchone()
            if existing:
                return dict(existing), True
            db.execute("""INSERT INTO documents(id,project_id,original_filename,stored_path,sha256,ingest_key,
                       category,business_date,month_day,document_number,version_label,source_document_id,status,created_at,updated_at,version_group)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (document_id, project_id, original_filename, str(path), digest, key, category, date, month_day,
                        document_number, version_label or stamp, source_document_id, "queued", stamp, stamp,
                        replacement["version_group"] if replacement else document_id))
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
            if row["status"] not in {"failed", "partial", "stored_only", "ready"}:
                raise ValueError("正在处理的文件不能重复排队")
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

    def finish(self, task, status, records=None, chunks=0, error="", parse_report=None):
        document = self.document(task["document_id"])
        with self.connect() as db:
            if records is not None:
                db.execute("DELETE FROM records WHERE document_id=?", (document["id"],))
                for record in records:
                    db.execute("""INSERT INTO records(id,document_id,project_id,sheet_name,row_number,record_number,business_date,month_day,date_raw,location,issue_text,requirement,responsible_party,reported_status,cells_json,date_quality,date_error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        record["id"], document["id"], document["project_id"], record["sheet_name"], record["row"],
                        record.get("record_number"), record.get("business_date"), record.get("month_day"), record.get("date_raw"),
                        record.get("location"), record.get("issue_text"), record.get("requirement"),
                        record.get("responsible_party"), record.get("reported_status"), json.dumps(record["cells"], ensure_ascii=False),
                        record.get("date_quality", "missing"), record.get("date_error", "")))
            if parse_report is not None:
                db.execute("UPDATE documents SET parse_report=? WHERE id=?", (json.dumps(parse_report, ensure_ascii=False), document["id"]))
            count = db.execute("SELECT COUNT(*) FROM records WHERE document_id=?", (document["id"],)).fetchone()[0]
            db.execute("UPDATE tasks SET status=?,error=?,finished_at=? WHERE id=?", (status, error, now(), task["id"]))
            db.execute("UPDATE documents SET status=?,error=?,chunk_count=?,record_count=?,updated_at=? WHERE id=?",
                       (status, error, chunks, count, now(), document["id"]))
            if status in {"ready", "partial", "stored_only"}:
                newest = db.execute("SELECT id FROM documents WHERE version_group=? AND status IN ('ready','partial','stored_only') ORDER BY created_at DESC,id DESC LIMIT 1",
                                    (document["version_group"],)).fetchone()[0]
                db.execute("UPDATE documents SET is_current=0 WHERE version_group=?", (document["version_group"],))
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
                      keyword=None, page=1, page_size=20, date_quality_filter=None):
        self.require_project(project_id)
        where = ["r.project_id=?", "d.status IN ('ready','partial')"]
        params = [project_id]
        if document_id:
            self.document(document_id, project_id)
            where.append("r.document_id=?")
            params.append(document_id)
        else:
            where.append("d.is_current=1")
        if reported_status == "unknown":
            where.append("(r.reported_status IS NULL OR r.reported_status='')")
        elif reported_status:
            where.append("r.reported_status=?")
            params.append(reported_status)
        if keyword:
            where.append("(instr(COALESCE(r.issue_text,''),?)>0 OR instr(r.cells_json,?)>0)")
            params.extend([keyword, keyword])
        if date_quality_filter == "needs_review":
            where.append("r.month_day IS NULL")
        scope_clause = " FROM records r JOIN documents d ON d.id=r.document_id WHERE " + " AND ".join(where)
        scope_params = list(params)
        if date:
            full, short = parse_business_date(date)
            where.append("r.business_date=?" if full else "r.month_day=?")
            params.append(full or short)
        clause = " FROM records r JOIN documents d ON d.id=r.document_id WHERE " + " AND ".join(where)
        with self.connect() as db:
            db.execute("BEGIN")
            unresolved = db.execute("SELECT COUNT(*)" + scope_clause + " AND r.month_day IS NULL", scope_params).fetchone()[0]
            unrecognized = db.execute("SELECT COUNT(*)" + scope_clause + " AND r.date_quality IN ('unrecognized','partial')", scope_params).fetchone()[0]
            total = db.execute("SELECT COUNT(*)" + clause, params).fetchone()[0]
            year_rows = db.execute("SELECT substr(r.business_date,1,4) AS year,COUNT(*) AS count" + clause + " GROUP BY year", params).fetchall()
            rows = db.execute("SELECT r.*,d.original_filename,d.version_label,d.document_number" + clause +
                              " ORDER BY d.created_at,d.id,r.sheet_name,r.row_number LIMIT ? OFFSET ?",
                              params + [page_size, (page - 1) * page_size]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["cells"] = json.loads(item.pop("cells_json"))
            items.append(item)
        years = {row["year"] or "未登记年份": row["count"] for row in year_rows}
        note = "没有年份的月日不会自动补年份；未登记的整改状态不等于已整改或未整改。"
        if date and not full:
            note += " 此次按月日跨年份匹配，年份分布：" + "、".join(f"{year}：{count}条" for year, count in years.items()) + "。"
        if unresolved:
            note += f" 当前文档范围还有 {unresolved} 条日期缺失/不完整/未识别记录（其中 {unrecognized} 条为未识别或缺少日）；按日结果不能保证涵盖这些行，请切换到待核对日期记录。"
        return {"total": total, "page": page, "page_size": page_size, "items": items,
                "unresolved_date_count": unresolved, "unrecognized_date_count": unrecognized, "year_distribution": years,
                "completeness": "date_unresolved" if date and unresolved else "matched_parsed_rows", "note": note}

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
            db.execute("INSERT INTO issue_events(id,issue_id,action,actor,note,attachment_ids,created_at) VALUES(?,?,?,?,?,?,?)",
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

    def add_issue_event(self, issue_id, action, actor, note, attachment_ids=None, evidence_date=""):
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
            day, _ = parse_business_date(evidence_date)
            if action in {"reply", "recheck_pass", "recheck_fail"} and not day:
                raise ValueError("整改回复与人工复查必须登记完整业务日期 YYYY-MM-DD")
            if day and day > datetime.now().date().isoformat():
                raise ValueError("处理依据日期不能晚于当前日期")
            source = db.execute("SELECT r.business_date,d.id,d.sha256 FROM records r JOIN documents d ON d.id=r.document_id WHERE r.id=?", (issue["record_id"],)).fetchone() if issue["record_id"] else None
            if day and source and source["business_date"] and day < source["business_date"]:
                raise ValueError("回复/复查日期不能早于来源检查日期")
            previous_reply = db.execute("SELECT evidence_date FROM issue_events WHERE issue_id=? AND action='reply' ORDER BY created_at DESC,id DESC LIMIT 1", (issue_id,)).fetchone()
            if action in {"recheck_pass", "recheck_fail"} and previous_reply and previous_reply[0] and day < previous_reply[0]:
                raise ValueError("复查日期不能早于本轮整改回复日期")
            evidence_category = "整改回复" if action == "reply" else "复查依据" if action == "recheck_pass" else None
            evidence_count = 0
            for document_id in attachment_ids:
                doc = db.execute("SELECT project_id,stored_path,status,category,business_date,id,sha256 FROM documents WHERE id=?", (document_id,)).fetchone()
                if not doc or doc["project_id"] != issue["project_id"]:
                    raise ValueError("附件不属于整改事项所在项目")
                if not Path(doc["stored_path"]).is_file() or doc["status"] not in {"ready", "partial", "stored_only"}:
                    raise ValueError("附件须完成入库或原件归档，且原件文件存在")
                if evidence_category and doc["category"] == evidence_category:
                    if source and (doc["id"] == source["id"] or doc["sha256"] == source["sha256"]):
                        raise ValueError("问题原表或其相同内容副本不能作为整改完成/复查通过的依据")
                    if day and doc["business_date"] and doc["business_date"] != day:
                        raise ValueError("处理日期与关联依据的登记业务日期不一致，请核对依据或日期")
                    evidence_count += 1
            if action in {"reply", "recheck_pass"} and not attachment_ids:
                raise ValueError("整改回复和复查通过须关联至少一份已归档的依据文件")
            if evidence_category and not evidence_count:
                raise ValueError(f"本次操作需至少一份分类为“{evidence_category}”的依据；其他资料只能作为参考")
            stamp = now()
            db.execute("INSERT INTO issue_events(id,issue_id,action,actor,note,attachment_ids,created_at,evidence_date) VALUES(?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, issue_id, action,
                       actor.strip(), note.strip(), json.dumps(attachment_ids), stamp, day or ""))
            db.execute("UPDATE issues SET status=?,updated_at=? WHERE id=?", (transitions[action][1], stamp, issue_id))
        return self.issue(issue_id)


_catalog = None


def get_catalog():
    global _catalog
    if _catalog is None:
        _catalog = DocumentCatalog()
    return _catalog
