import streamlit as st
from ui import inject_styles, page_header, render_sidebar, api_request, project_selector

st.set_page_config(page_title="工程项目RAG智能问答系统", page_icon="▣", layout="wide", initial_sidebar_state="expanded")
inject_styles()
render_sidebar("项目总览")
page_header("CONSTRUCTION RAG WORKBENCH", "工程项目RAG智能问答系统", "工程资料查询、完整记录台账与现场整改资料闭环")
project = project_selector()
response = api_request("GET", "/documents/stats", params={"project_id": project}, timeout=5)
stats = response.json() if response is not None and response.ok else {}
cols = st.columns(4)
for col, title, key in zip(cols, ["原件版本", "当前文档", "完整记录", "当前索引片段"],
                           ["document_count", "current_document_count", "record_count", "indexed_chunks"]):
    col.metric(title, stats.get(key, "—"))
st.subheader("项目工作台")
cols = st.columns(2)
with cols[0]:
    st.page_link("pages/1_💬_问答.py", label="智能问答", icon="💬")
    st.write("查询监理资料与规范说明，按项目、文档版本检索并展示来源。")
    st.page_link("pages/4_📋_记录查询.py", label="完整记录查询", icon="📋")
    st.write("按日期与原表字段筛选完整清单，导出全部匹配行；记录总数不受 top-k 限制。")
with cols[1]:
    st.page_link("pages/2_📁_知识库管理.py", label="文档台账与入库状态", icon="📁")
    st.write("登记原件、分类、业务日期、版本和导出件关联，查看排队、解析、索引及失败原因。")
    st.page_link("pages/5_🛠️_现场整改.py", label="现场整改资料闭环", icon="🛠️")
    st.write("问题登记、整改回复、人工复查与销项，保留操作记录和归档依据。")
st.subheader("当前文件能力")
st.info("文字 PDF、DOCX、Excel、TXT、Markdown：解析与检索。DXF：直接文字/属性的部分解析。DWG、RVT、IFC：首期原件归档，关联导出件后查询。现场图片可作整改依据。")
st.caption("扫描件 OCR、BIM 属性解析、账号权限与电子签章尚未实施。仅原件归档不等于内容可检索。")
model = api_request("GET", "/system/model_status", timeout=5)
if model is not None and model.ok:
    info = model.json()
    st.caption(f"问答模型：{info.get('provider', '未登记')} / {info.get('model', '未登记')} · {info.get('message', '')}")
st.caption("启动顺序：API → 前端；云模型在 rag_app/config/.env 配置，本地模型需先运行模型服务。")
