# 工程项目 RAG 智能问答系统

当前版本：1.1.1。面向施工、监理工作的本地作品集应用，沿用项目一与“监理智查”的 FastAPI / LangChain / Chroma / Streamlit 实现，新增**完整记录查询、文档台账、持久化入库任务、现场整改资料闭环**。

独立图纸错误审查已移出主导航与主 API，源代码保存为历史实验。现场问题通过问题记录、整改回复、申请复查及人工销项处理。系统不会因模型回答、照片或原表空白状态自动销项。

## Windows 启动

进入实际包含 `run_api.py` 的 `rag_app` 目录，在两个终端运行：

```bat
conda activate rag_qa_system
cd /d "C:\Users\32978\Desktop\工程项目RAG智能问答系统_整合版项目一\rag_app"
python run_api.py
```

```bat
conda activate rag_qa_system
cd /d "C:\Users\32978\Desktop\工程项目RAG智能问答系统_整合版项目一\rag_app"
python run_frontend.py
```

前端：`http://localhost:8501`；接口文档：`http://localhost:8000/docs`。

首次安装需 `python -m pip install -r requirements.txt`。仅当 `config/.env` 不存在时，从 `config/.env.example` 复制并填写配置，避免覆盖已有密钥。云模型无需 Ollama；本地默认问答模型 `qwen2.5:0.5b` 需要通过 `ollama pull` 安装。Embedding 使用本地 BGE 模型或首次从 Hugging Face 下载，权重放 `rag_app/models/BAAI_bge-small-zh-v1.5`。模型权重不在代码 ZIP 中。

## 能力与边界

| 类型/功能 | 当前能力 |
|---|---|
| 文字 PDF、DOCX、TXT、Markdown | 解析分块、语义检索与来源 |
| XLSX/XLS | 完整原表记录存 SQLite，语义片段存 Chroma；按日期、文档、原表状态、关键词查询全部匹配行及 CSV |
| DXF | 读取布局中的直接 TEXT/MTEXT 和 INSERT 属性，标记部分解析；不保证嵌套块、外参、代理对象完整 |
| DWG | 原件归档；另传 DXF/PDF，可关联原件 |
| RVT | 原件归档；首期通过 Revit 导出 IFC/PDF 并关联原件 |
| IFC | 原件归档，暂未实现 BIM 属性解析 |
| DOC、PNG/JPG/JPEG | 原件归档；DOC 可另存 DOCX/PDF，现场图片可关联整改依据 |
| 扫描 PDF | 未包含 OCR；未提取文字时明确标为仅归档 |
| 业务日期 | 支持常见分隔符与中文数字；缺日/未识别明确计数，月日查询展示年份分布，不补齐年份或日 |
| 文档版本 | 同名文件默认独立保存；明确选择替换/修订才形成版本组，默认查询各组最新成功版本 |
| 入库任务 | SQLite 排队、解析、索引、可用、部分解析、仅归档、失败；重启恢复中断任务，可手动重试 |
| 整改闭环 | 人工登记、回复、申请复查、复查通过/退回、重新打开；回复和销项需要指定用途的归档依据与完整业务日期，原问题表不能代替完成依据 |

单文件默认上限 50MB。上传已接收不等于已经可检索，应在台账确认状态。索引失败但 Excel 解析成功时，完整记录仍可查询，语义索引数为零。仅原件归档的 DWG/RVT/IFC 不会作为文字问答来源。

当前是单 API 进程、本地单用户应用。项目范围过滤已实现，但没有账号认证、RBAC 或电子签章；填写的操作人不代表认证身份。尚无多进程任务租约、生产部署规模或工程规范准确率数据。FAISS 两种检索接口及 LangChain 检索器使用元数据谓词，真实 FAISS 范围过滤回归已通过；真实 HTTP 集成使用 Chroma。

## 核心代码

| 文件 | 作用 |
|---|---|
| `rag_app/core/document_catalog.py` | SQLite 项目、文档版本、任务、完整记录、人工事件 |
| `rag_app/core/file_ingestion.py` | 类型验证、表格字段与日期、DXF 部分解析、单进程 Worker |
| `rag_app/api/routes/documents.py` | 台账、下载、完整记录分页/导出、整改状态接口 |
| `rag_app/api/routes/qa.py` | 日期清单查询走结构化数据库；语义问答才初始化 LLM |
| `rag_app/core/rag_chain.py` | 检索限定当前项目/版本文档 ID，对话按项目与文档隔离 |
| `rag_app/frontend/pages/4_📋_记录查询.py` | 完整清单、原表字段、导出和登记整改事项 |
| `rag_app/frontend/pages/5_🛠️_现场整改.py` | 人工闭环、依据关联、事件历史与 MD 导出 |
| `rag_app/experiments/drawing_review/` | 历史独立图纸审查，显式启动才能访问 |

旧 `/knowledge/delete`、`/knowledge/clear` 已返回 409，避免只清除向量导致台账与整改依据不一致。原件不自动删除。已有上传原件启动时导入默认项目，重复内容复用文档 ID；旧的无文档 ID 向量保留，但主产品检索只使用台账中的文档 ID。

## 验证

```bat
cd rag_app
python -m unittest discover -s tests -p "test_*.py" -v
cd ..
python integration/verify_workbench.py --model-dir rag_app/models/BAAI_bge-small-zh-v1.5
```

集成验证只使用隔离合成資料，涵盖真实 HTTP、Chroma、本地 Ollama、服务重启和 Streamlit AppTest。DWG/RVT/IFC 的合成文件仅验证基础文件头与归档状态，不代表完整原生文件解析。结果见 [工作台回归验证](docs/工作台回归验证.json)。历史图纸实验测试与旧验证记录不作为本版业务验收。

源码与面试资料：[实现说明与面经](docs/源码改动与面试面经.md)、[原始源码](docs/项目一原始源码归档.md)、[修改后源码](docs/修改后整合源码归档.md)、[逐文件改动](docs/项目一到整合版改动对照.md)、[用户手册](docs/用户手册_资料台账与现场整改.md)。

原仓库 `upstream/`、`cad-spatial-analysis/` 保留来源与许可证，当前不参与主业务流程。参考开源项目的功能模式没有被描述为自行开发的原始算法。

## 1.1.1 不规整表格修复

34 项自动回归和 66 项真实集成检查通过，包含真实 FAISS 元数据范围过滤。解析与日期待核对数量明确展示，不宣称任意复杂 Excel 都能完整自动理解。按日期结果不包含无法确定日期的行，须查看待核对清单。无可检索文档或空召回不调用问答模型；非空相似片段的相关性和工程适用性仍需评估。

证据见 [审查修复说明](docs/审查反馈修复与验证_2026-10-08.md)、[上一版缺陷复现](docs/上一版缺陷复现_2026-10-08.json)、[真实合成资料服务日志](docs/工作台集成服务日志_2026-10-08.txt)。课程演示移至 `rag_app/examples/course/`。
