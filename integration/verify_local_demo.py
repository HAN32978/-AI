"""Run an isolated upload -> real embedding -> CAD evidence HTTP smoke check."""

import argparse
import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    model = args.model_dir.resolve()
    if not model.is_dir():
        parser.error("--model-dir 必须是已下载的 Embedding 模型目录")
    runtime = repo / ".runtime" / "verification"
    runtime.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "EMBEDDING_MODEL_NAME": str(model), "USE_RERANKER": "false",
        "VECTOR_DB_DIR": str(runtime / run_id / "vectors"), "UPLOAD_DIR": str(runtime / run_id / "upload"),
        "LOG_FILE": str(runtime / "api.log"),
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    })
    import sys
    base = f"http://127.0.0.1:{port}/api/v1"
    report = {}
    with (runtime / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=repo / "rag_app", env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("API 启动失败，见 .runtime/verification/server.log")
                try:
                    if requests.get(base + "/system/health", timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            else:
                raise TimeoutError("API 启动超时，见 .runtime/verification/server.log")
            response = requests.post(base + "/upload/file", files={
                "file": ("demo_only.txt", "演示资料：疏散门和楼梯的图纸问题需要核查，模拟数据不构成工程依据。".encode("utf-8")),
            }, data={"category": "演示资料"}, timeout=15)
            response.raise_for_status()
            report["upload_http_status"] = response.status_code
            for _ in range(30):
                stats = requests.get(base + "/knowledge/stats", timeout=5).json()
                if stats.get("total_documents", 0) > 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("演示文档未完成向量入库")
            issues_path = repo / "integration" / "output" / "cad_issues.json"
            issues = json.loads(issues_path.read_text(encoding="utf-8"))["issues"]
            response = requests.post(base + "/review/evidence", json={
                "project_name": "本地集成演示", "issues": issues, "top_k": 1,
            }, timeout=30)
            response.raise_for_status()
            result = response.json()
            assert result["summary"]["total"] == len(issues)
            assert all(packet["candidate_sources"] for packet in result["issues"])
            assert all("demo_only.txt" in packet["candidate_sources"][0]["source"] for packet in result["issues"])
            report.update({"review_http_status": response.status_code, "cad_issues": len(issues), "indexed_chunks": stats["total_documents"]})
            invalid = requests.post(base + "/review/evidence", json={"issues": [{}]}, timeout=5)
            assert invalid.status_code == 422
            report["invalid_issue_http_status"] = invalid.status_code
            os.environ["RAG_API_BASE"] = base
            sys.path.insert(0, str(repo / "rag_app" / "frontend"))
            from streamlit.testing.v1 import AppTest
            page = AppTest.from_file(str(repo / "rag_app" / "frontend" / "app.py"), default_timeout=20).run()
            assert not page.exception, str(page.exception)
            page.switch_page("pages/4_🧭_图纸审查.py")
            page.session_state["review_result"] = result
            page.run()
            assert not page.exception, str(page.exception)
            report["streamlit_page_runtime"] = "passed"
            report["status"] = "passed"
            (runtime / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
