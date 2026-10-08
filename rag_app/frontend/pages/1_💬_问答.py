import uuid

import streamlit as st

from ui import (
    API_BASE,
    api_request,
    inject_styles,
    page_header,
    render_sidebar,
    render_sources,
    project_selector,
    document_choices,
    document_label,
)


st.set_page_config(page_title="智能问答 | 工程项目RAG智能问答系统", page_icon="▣", layout="wide")
inject_styles()
render_sidebar("智能问答")
page_header("FIELD ASSISTANT", "智能问答", "用自然语言查询监理资料、施工图纸说明与规范条文，并保留可复核的引用依据")

project = project_selector()
documents = {d["id"]: d for d in document_choices(project) if d["status"] in {"ready", "partial"}}
document_id = st.selectbox("问答范围", [""] + list(documents),
                           format_func=lambda v: "当前项目全部可检索的当前版本" if not v else document_label(documents[v]))
scope = (project, document_id)
if st.session_state.get("chat_scope") != scope:
    st.session_state.messages = []
    st.session_state.chat_scope = scope
query_mode = st.selectbox("查询方式", ["auto", "records", "semantic"],
                          format_func=lambda v: {"auto": "自动：日期记录查询走完整清单", "records": "完整记录查询（无需模型）", "semantic": "知识库语义问答"}[v])
scope_params = {"project_id": project, **({"document_id": document_id} if document_id else {})}


def normalize_messages(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items or []:
        role = item.get("role", "assistant")
        if role == "human":
            role = "user"
        normalized.append(
            {
                "role": role,
                "content": item.get("content", ""),
                "sources": item.get("sources", []),
                "intent": item.get("intent", ""),
            }
        )
    return normalized


if "sessions" not in st.session_state:
    st.session_state.sessions = {}
if "current_session" not in st.session_state:
    st.session_state.current_session = str(uuid.uuid4())
    st.session_state.sessions[st.session_state.current_session] = "现场查询"
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.markdown("<div class='section-label' style='color:#fff'>会话管理</div>", unsafe_allow_html=True)
    session_ids = list(st.session_state.sessions.keys())
    current_index = session_ids.index(st.session_state.current_session)
    selected = st.selectbox(
        "当前会话",
        session_ids,
        index=current_index,
        format_func=lambda session_id: st.session_state.sessions[session_id],
        label_visibility="collapsed",
    )
    if selected != st.session_state.current_session:
        st.session_state.current_session = selected
        history_response = api_request(
            "GET",
            "/qa/history",
            params={"session_id": selected, **scope_params},
            timeout=5,
        )
        st.session_state.messages = normalize_messages(
            history_response.json().get("history", []) if history_response is not None and history_response.ok else []
        )
        st.rerun()

    if st.button("＋ 新建查询会话", use_container_width=True):
        new_id = str(uuid.uuid4())
        st.session_state.sessions[new_id] = f"查询 {len(st.session_state.sessions) + 1}"
        st.session_state.current_session = new_id
        st.session_state.messages = []
        st.rerun()

    new_name = st.text_input(
        "会话名称",
        value=st.session_state.sessions[st.session_state.current_session],
        label_visibility="collapsed",
        placeholder="输入会话名称",
    )
    if new_name and new_name != st.session_state.sessions[st.session_state.current_session]:
        st.session_state.sessions[st.session_state.current_session] = new_name

    if st.button("清除当前会话", use_container_width=True):
        response = api_request(
            "POST",
            "/qa/clear_memory",
            params={"session_id": st.session_state.current_session, **scope_params},
            timeout=10,
        )
        st.session_state.messages = []
        if response is not None and response.ok:
            st.toast("当前会话已清除")
        else:
            st.warning("本地界面已清除，但后端记忆未确认，请检查 API 服务")
        st.rerun()

    st.divider()
    st.caption("推荐提问")
    st.markdown(
        """
        <div style="color:#b8c7d6;font-size:.8rem;line-height:1.75">
        · 这份施工方案有哪些监理控制要点？<br/>
        · 钢筋隐蔽验收需要检查哪些资料？<br/>
        · 规范对旁站记录有哪些要求？<br/>
        · 帮我定位图纸中的材料与做法说明
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    "<div class='status-pill status-neutral'>知识库检索</div><div class='status-pill status-ok'>引用可追溯</div>",
    unsafe_allow_html=True,
)

model_response = api_request("GET", "/system/model_status", timeout=5)
if model_response is not None and model_response.ok:
    model_state = model_response.json()
    if model_state.get("status") == "unavailable":
        st.warning(model_state.get("message", "模型服务暂不可用"))

for message in st.session_state.messages:
    role = message.get("role", "assistant")
    with st.chat_message("user" if role == "user" else "assistant"):
        if message.get("intent") in {"连接失败", "请求失败", "系统错误"}:
            st.error(message.get("content", "请求失败"))
        else:
            st.markdown(message.get("content", ""))
        if message.get("intent"):
            st.caption(f"意图：{message['intent']}")
        render_sources(message.get("sources", []))

if not st.session_state.messages:
    st.info("输入一个工程问题开始查询。系统会优先检索已上传的监理资料，并在回答下方展示引用依据。")

if prompt := st.chat_input("例如：地下室防水施工的旁站监理要点有哪些？"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("正在检索工程资料并生成回答…"):
            response = api_request(
                "POST",
                "/qa/ask",
                json={"question": prompt, "session_id": st.session_state.current_session, "query_mode": query_mode, **scope_params},
                timeout=120,
            )
            if response is None:
                answer = f"无法连接 API 服务或请求超时。请检查后端地址 {API_BASE} 和后端日志。"
                sources = []
                intent = "连接失败"
                st.error(answer)
            elif not response.ok:
                try:
                    detail = response.json().get("detail", "后端请求失败")
                except ValueError:
                    detail = "后端请求失败，请检查日志"
                answer = f"请求失败（{response.status_code}）：{detail}"
                sources = []
                intent = "请求失败"
                st.error(answer)
            else:
                data = response.json()
                answer = data.get("answer") or "模型未返回有效回答，请检查模型服务。"
                sources = data.get("sources", [])
                intent = data.get("intent", "")
                st.markdown(answer)
                if intent:
                    st.caption(f"意图：{intent}")
                render_sources(sources)

            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "sources": sources, "intent": intent}
            )
