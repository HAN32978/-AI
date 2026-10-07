"""隔离知识库验证 Excel 上传、真实 Ollama 问答和引用来源。"""
import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import requests
from openpyxl import Workbook


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    runtime = repo / ".runtime" / "qa-verification" / uuid.uuid4().hex[:12]
    runtime.mkdir(parents=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update({"EMBEDDING_MODEL_NAME": str(args.model_dir.resolve()),
                "VECTOR_DB_DIR": str(runtime / "vectors"), "UPLOAD_DIR": str(runtime / "upload"),
                "LOG_FILE": str(runtime / "api.log"), "USE_RERANKER": "false",
                "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "LLM_PROVIDER": "ollama", "OLLAMA_MODEL_NAME": "qwen2.5:0.5b"})
    base = f"http://127.0.0.1:{port}/api/v1"
    with (runtime / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
                                   cwd=repo / "rag_app", env=env, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"API 启动失败：{runtime}")
                try:
                    if requests.get(base + "/system/health", timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            else:
                raise TimeoutError("API 启动超时")
            ready = requests.get(base + "/system/model_status", timeout=5).json()
            assert ready["status"] == "ready", ready
            workbook = Workbook()
            workbook.active.title = "演示检查记录"
            workbook.active.append(["检查日期", "位置", "检查问题", "处理要求"])
            workbook.active.append(["9月9日", "测试区A", "演示通道堆放材料", "清理通道内材料"])
            buffer = io.BytesIO()
            workbook.save(buffer)
            workbook.close()
            uploaded = requests.post(base + "/upload/file", files={"file": ("qa_demo_only.xlsx", buffer.getvalue())}, timeout=20)
            uploaded.raise_for_status()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                stats = requests.get(base + "/knowledge/stats", timeout=5).json()
                if stats.get("total_documents", 0) >= 1:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Excel 未完成入库")
            response = requests.post(base + "/qa/ask", json={
                "question": "请根据演示检查记录，回答9月9日测试区A发现的检查问题和处理要求。", "session_id": "qa-regression"
            }, timeout=120)
            response.raise_for_status()
            answer = response.json()
            assert answer["answer"].strip(), answer
            assert "材料" in answer["answer"] and "清理" in answer["answer"], answer
            assert answer["sources"] and all("qa_demo_only.xlsx" in source["source"] for source in answer["sources"]), answer
            report = {"status": "passed", "model": "qwen2.5:0.5b", "model_status": ready["status"],
                      "xlsx_upload_http_status": uploaded.status_code, "indexed_chunks": stats["total_documents"],
                      "qa_http_status": response.status_code, "answer": answer["answer"], "source_count": len(answer["sources"]),
                      "scope": "合成 Excel 的真实本地问答与引用验证；未评估工程规范准确率"}
            (repo / "docs" / "问答回归验证.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
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
