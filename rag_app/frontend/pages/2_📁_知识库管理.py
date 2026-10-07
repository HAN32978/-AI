import time

import streamlit as st

from ui import api_request, inject_styles, page_header, render_sidebar


st.set_page_config(page_title="资料库管理 | 工程项目RAG智能问答系统", page_icon="▤", layout="wide")
inject_styles()
render_sidebar("资料库管理")
page_header("DOCUMENT CONTROL", "资料库管理", "上传和维护项目监理资料，建立可检索、可追溯的工程知识库")


def show_stats() -> None:
    response = api_request("GET", "/knowledge/stats", timeout=10)
    if response is None or not response.ok:
        st.warning("暂时无法读取知识库统计，请确认 API 服务已启动。")
        return
    data = response.json()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("已索引片段", data.get("total_documents", 0))
    with col2:
        st.metric("向量引擎", str(data.get("vector_store_type", "—")).upper())
    with col3:
        st.metric("检索状态", "可用")
    st.caption(f"持久化路径：{data.get('persist_directory', '—')}")


tab_upload, tab_stats, tab_maintenance = st.tabs(["上传资料", "知识库状态", "维护操作"])

with tab_upload:
    st.markdown("<div class='section-label'>资料入库</div>", unsafe_allow_html=True)
    st.markdown(
        "支持 PDF、Word、Excel、Markdown 和 TXT。上传后系统会在后台完成文本解析、分块、向量化和入库。",
    )
    uploaded_files = st.file_uploader(
        "选择项目资料",
        type=["pdf", "docx", "doc", "txt", "md", "xlsx", "xls"],
        accept_multiple_files=True,
        help="建议按项目或资料类型分批上传，便于后续检索和维护。",
    )
    category = st.selectbox(
        "资料分类",
        [
            "安全监理",
            "质量控制",
            "施工方案",
            "图纸资料",
            "规范标准",
            "监理规划与细则",
            "会议纪要与报审资料",
            "其他",
        ],
    )
    if st.button("开始入库", type="primary", use_container_width=True):
        if not uploaded_files:
            st.warning("请先选择要上传的资料。")
        else:
            progress = st.progress(0, text="正在准备资料…")
            success, failed = 0, 0
            for index, file in enumerate(uploaded_files, start=1):
                progress.progress((index - 1) / len(uploaded_files), text=f"正在处理 {file.name}…")
                response = api_request(
                    "POST",
                    "/upload/file",
                    files={"file": (file.name, file.getvalue())},
                    data={"category": category},
                    timeout=120,
                )
                if response is not None and response.ok:
                    success += 1
                    st.toast(f"已提交：{file.name}")
                else:
                    failed += 1
                    st.warning(f"上传失败：{file.name}")
            progress.progress(1.0, text="资料提交完成")
            if success:
                st.success(f"成功提交 {success} 份资料，后台正在建立索引。")
            if failed:
                st.error(f"有 {failed} 份资料提交失败，请检查 API 日志。")

    st.markdown("<div class='section-label'>资料入库建议</div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="feature-card">
        <div class="feature-text">文件名建议包含项目、专业和版本，例如：<b>XX项目_地下室防水施工方案_V2.pdf</b>。<br/>图纸建议按专业和图号归档；规范资料建议注明年份和版本，便于查询结果复核。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_stats:
    st.markdown("<div class='section-label'>知识库运行状态</div>", unsafe_allow_html=True)
    if st.button("刷新状态", use_container_width=True):
        st.rerun()
    show_stats()

with tab_maintenance:
    st.markdown("<div class='section-label'>维护操作</div>", unsafe_allow_html=True)
    st.warning("清空知识库会删除当前向量索引，上传文件本身不会自动删除。请确认后再执行。")
    if "confirm_clear" not in st.session_state:
        st.session_state.confirm_clear = False
    if st.button("申请清空向量索引", use_container_width=True):
        st.session_state.confirm_clear = True
    if st.session_state.confirm_clear:
        st.error("确认要清空当前知识库索引吗？")
        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button("确认清空", type="primary", use_container_width=True):
                response = api_request("POST", "/knowledge/clear", timeout=60)
                if response is not None and response.ok:
                    st.success("知识库索引已清空。")
                else:
                    st.error("清空失败，请检查 API 服务和日志。")
                st.session_state.confirm_clear = False
        with cancel_col:
            if st.button("取消", use_container_width=True):
                st.session_state.confirm_clear = False
                st.rerun()
