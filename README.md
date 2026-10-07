# 工程项目RAG智能问答系统

面向工程项目资料查询与图纸问题复核的本地作品集项目。仓库整合了三个已有部分：项目一的 FastAPI/LangChain RAG 核心、此前修改的“监理智查”界面与配置、原仓库导入的 CAD 审查上游代码。当前集成点是**审图问题池 JSON → 工程资料检索 → 候选依据展示 → 人工复核**。

## 模块

| 路径 | 作用 |
|---|---|
| `rag_app/` | 可独立运行的工程资料 RAG 应用，包含问答、上传、知识库和图纸审查工作流页面 |
| `upstream/` | 已有的 AI-CAD-Audit-System 上游审图代码，保留原许可证 |
| `cad-spatial-analysis/` | 已有的空间分析代码与参考资料，保留原许可证 |
| `integration/export_cad_issues.py` | 调用上游审图入口，导出 `ProblemPool.to_json()` 格式的问题池 |
| `integration/examples/demo_issues.json` | 明确标记为模拟数据的接口示例 |
| `docs/源码改动与面试面经.md` | 源码关系、实现讲解、面试问答和验证边界 |

## 快速运行（Windows PowerShell）

RAG 应用与上游 CAD 模块的依赖分开安装；Python 建议使用 3.10 环境。

```powershell
cd rag_app
python -m pip install -r requirements.txt
Copy-Item config/.env.example config/.env
# 按本机 Ollama 模型或云端服务修改 config/.env
python run_api.py
```

在另一个终端：

```powershell
cd rag_app
python run_frontend.py
```

打开 `http://localhost:8501`。接口文档在 `http://localhost:8000/docs`。需要本地 Embedding 模型：可将已有 `BAAI_bge-small-zh-v1.5` 模型目录放入 `rag_app/models/`，也可在有网络时由 Hugging Face 下载。模型权重、`.env`、上传文件和向量库均不提交到仓库。

## 图纸审查与 RAG 的组合

先用仓库附带的模拟 JSON 验证接口：在“图纸审查工作流”页面上传 `integration/examples/demo_issues.json`，点击“检索候选依据”。需要 RAG API 和可用的 Embedding 模型；未上传相关资料时会显示“待补充依据”。

要从上游 CAD 审查代码生成问题池，先安装其独立依赖：

```powershell
python -m pip install -r upstream/v7/requirements.txt
python integration/export_cad_issues.py --mode demo
```

输出在 `integration/output/cad_issues.json`，然后在前端上传。真实 DXF 审查可用 `--mode dxf --dxf-dir <图纸目录> --project <项目名>`；此模式需要上游要求的模型配置，当前未用真实图纸和规范资料完成端到端验证。

也可以直接调用 `POST /api/v1/review/evidence`，请求体包含 `project_name`、`issues` 和 `top_k`。`issues` 使用上游 `ProblemPool.to_json()` 的同名数组。系统返回候选资料片段与复核状态，不自动作出合规结论。

## 验证与边界

```powershell
cd rag_app
python -m unittest discover -s tests -p test_review_workflow.py -v
```

已通过两个接口函数测试、Python 编译检查，以及本地模拟资料的 HTTP 集成检查：上游导出 7 条模拟问题，资料上传后经真实 Embedding 写入 Chroma，审查接口返回候选来源；Streamlit 首页与带结果的工作流页面运行检查通过。真实 DXF、真实规范库、模型回答质量和工程结论尚未验证。`integration/examples/` 的数值与条款只能用于演示数据流。

源码阅读材料：[原始代码](docs/项目一原始源码归档.md)、[修改后代码](docs/修改后整合源码归档.md)、[逐文件差异](docs/项目一到整合版改动对照.md)、[面试讲解](docs/源码改动与面试面经.md)。

详细架构和操作见 [集成说明](docs/INTEGRATION.md)。
