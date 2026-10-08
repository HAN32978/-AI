import streamlit as st

from ui import api_request, inject_styles, ollama_status, page_header, render_sidebar


st.set_page_config(page_title="系统设置 | 工程项目RAG智能问答系统", page_icon="⚙", layout="wide")
inject_styles()
render_sidebar("系统设置")
page_header("RUNTIME CONFIGURATION", "系统设置", "查看本地模型、检索参数和服务状态；修改配置后请重启 API 服务")


health_response = api_request("GET", "/system/health", timeout=4)
config_response = api_request("GET", "/system/config", timeout=4)
config = config_response.json() if config_response is not None and config_response.ok else {}
ollama_ok, ollama_models = ollama_status()

col1, col2 = st.columns(2)
with col1:
    st.markdown("<div class='section-label'>服务状态</div>", unsafe_allow_html=True)
    if health_response is not None and health_response.ok:
        st.success(f"API 在线 · {health_response.json().get('version', 'unknown')}")
    else:
        st.error("API 未连接 · 请先启动 FastAPI")
with col2:
    st.markdown("<div class='section-label'>Ollama 状态</div>", unsafe_allow_html=True)
    if ollama_ok:
        st.success(f"Ollama 在线 · 已发现 {len(ollama_models)} 个模型")
    else:
        st.warning("Ollama 未连接 · 请运行 ollama serve")

st.markdown("<div class='section-label'>当前运行配置</div>", unsafe_allow_html=True)
config_col1, config_col2, config_col3 = st.columns(3)
with config_col1:
    st.metric("LLM 提供商", config.get("llm_provider", "—"))
    st.metric("向量引擎", config.get("vector_store_type", "—"))
with config_col2:
    st.metric("当前模型", config.get("llm_model", "—"))
    st.metric("Embedding", config.get("embedding_model", "—"))
with config_col3:
    st.metric("检索 Top-K", config.get("search_top_k", "—"))
    st.metric("分块大小", config.get("chunk_size", "—"))

st.markdown("<div class='section-label'>本地启动方式</div>", unsafe_allow_html=True)
st.code(
    """# 终端 1：启动 Ollama（如果服务尚未运行）
ollama serve

# 终端 2：确认本地模型
ollama list

# 终端 3：启动 API
python run_api.py

# 终端 4：启动 Streamlit 前端
python run_frontend.py""",
    language="powershell",
)

st.info("实际模型提供商以当前运行配置为准。模型与密钥在 config/.env 中维护，修改后重启 API。云模型无需启动 Ollama；完整记录查询无需调用问答模型。")

st.markdown("<div class='section-label'>可接入提供商</div>", unsafe_allow_html=True)
provider_cards = [
    ("Ollama（本地）", "OLLAMA_BASE_URL", "http://localhost:11434", "无需云端 API Key，适合内网资料"),
    ("OpenAI", "OPENAI_BASE_URL", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    ("DeepSeek", "DEEPSEEK_BASE_URL", "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    ("硅基流动", "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY"),
    ("阿里云百炼", "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    ("智谱 AI", "ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY"),
    ("Moonshot / Kimi", "MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY"),
    ("MiniMax", "MINIMAX_BASE_URL", "https://api.minimaxi.com/v1", "MINIMAX_API_KEY"),
    ("腾讯混元", "HUNYUAN_BASE_URL", "https://api.hunyuan.cloud.tencent.com/v1", "HUNYUAN_API_KEY"),
    ("自定义兼容接口", "CUSTOM_BASE_URL", "由你填写", "CUSTOM_API_KEY"),
]
for name, env_name, base_url, note in provider_cards:
    st.markdown(
        f'<div class="evidence-card"><div class="evidence-source">{name}</div><div class="evidence-text"><b>{env_name}</b> · {base_url}<br/>{note}</div></div>',
        unsafe_allow_html=True,
    )

if ollama_models:
    st.markdown("<div class='section-label'>本地模型清单</div>", unsafe_allow_html=True)
    for model in ollama_models:
        st.markdown(f"<span class='status-pill status-neutral'>{model}</span>", unsafe_allow_html=True)
