import streamlit as st

from ui import inject_styles, page_header, render_sidebar, api_request, ollama_status

st.set_page_config(
    page_title="工程项目RAG智能问答系统",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_styles()
render_sidebar("项目总览")
page_header("CONSTRUCTION RAG WORKBENCH", "工程项目RAG智能问答系统", "工程资料查询、图纸问题与候选依据复核工作台")

stats_response = api_request("GET", "/knowledge/stats", timeout=4)
health_response = api_request("GET", "/system/health", timeout=4)
stats = stats_response.json() if stats_response is not None and stats_response.ok else {}
health = health_response.json() if health_response is not None and health_response.ok else {}
ollama_ok, ollama_models = ollama_status()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-label">知识库片段</div><div class="metric-value">{stats.get("total_documents", "—")}</div><div class="metric-note">已索引文档片段</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="metric-label">向量引擎</div><div class="metric-value">{str(stats.get("vector_store_type", "—")).upper()}</div><div class="metric-note">本地持久化检索</div></div>', unsafe_allow_html=True)
with col3:
    status = "在线" if health else "待启动"
    st.markdown(f'<div class="metric-card"><div class="metric-label">API 服务</div><div class="metric-value">{status}</div><div class="metric-note">FastAPI · localhost:8000</div></div>', unsafe_allow_html=True)
with col4:
    model_status = "已连接" if ollama_ok else "未连接"
    st.markdown(f'<div class="metric-card"><div class="metric-label">Ollama</div><div class="metric-value">{model_status}</div><div class="metric-note">{len(ollama_models)} 个本地模型</div></div>', unsafe_allow_html=True)

st.markdown("<div class='section-label'>工作台入口</div>", unsafe_allow_html=True)
features = st.columns(3)
cards = [
    ("智能问答", "针对监理资料、图纸说明和规范条文提问，答案附带引用依据。", "前往问答  →"),
    ("资料库管理", "上传 PDF、Word、Excel、Markdown 等项目资料，自动切分并建立索引。", "管理资料  →"),
    ("图纸审查工作流", "导入 CAD 审查问题，匹配知识库候选依据并交由人工复核。", "开始复核  →"),
]
for column, (title, body, action) in zip(features, cards):
    with column:
        st.markdown(f'<div class="feature-card"><div class="feature-title">{title}</div><div class="feature-text">{body}<br/><span style="color:#b7791f;font-weight:700">{action}</span></div></div>', unsafe_allow_html=True)

st.markdown("<div class='section-label'>适用场景</div>", unsafe_allow_html=True)
left, right = st.columns([1.1, 1])
with left:
    st.markdown(
        """
        <div class="feature-card">
        <div class="feature-title">从资料堆到可追溯结论</div>
        <div class="feature-text">把监理规划、监理细则、施工方案、旁站记录、验收资料、设计图纸说明和规范标准集中到一个本地知识库。每次回答保留文件名、页码和原文片段，方便复核与现场沟通。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        """
        <div class="feature-card">
        <div class="feature-title">建议启动顺序</div>
        <div class="feature-text"><b>1</b> 启动 Ollama　<b>2</b> 启动 FastAPI　<b>3</b> 上传项目资料　<b>4</b> 开始查询<br/><span style="color:#627d98">当前项目适合作为监理行业 RAG MVP / 作品集项目继续迭代。</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)
st.caption("工程项目RAG智能问答系统 · 工程资料查询与图纸审查工作流")
