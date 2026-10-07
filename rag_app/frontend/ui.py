"""共享前端组件：监理智查的视觉样式、API 请求和页面框架。"""

import os
from html import escape
from typing import Any

import requests
import streamlit as st


API_BASE = os.getenv("RAG_API_BASE", "http://localhost:8000/api/v1")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def inject_styles() -> None:
    """注入适合监理行业的深蓝、灰白、琥珀色视觉系统。"""
    st.markdown(
        """
        <style>
        :root {
            --navy: #102a43;
            --navy-2: #163b5c;
            --ink: #1f2933;
            --muted: #627d98;
            --line: #d9e2ec;
            --paper: #f7f9fb;
            --amber: #b7791f;
            --green: #257942;
        }
        .stApp { background: var(--paper); color: var(--ink); }
        [data-testid="stHeader"] { background: rgba(247,249,251,.9); }
        [data-testid="stSidebar"] { background: var(--navy); }
        [data-testid="stSidebarNav"] { display: none; }
        [data-testid="stSidebar"] * { color: #e6eef5; }
        [data-testid="stSidebar"] .stButton button {
            border: 1px solid rgba(255,255,255,.18);
            background: rgba(255,255,255,.08);
            color: #fff;
        }
        [data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,.16); }
        h1, h2, h3 { color: var(--navy); letter-spacing: -.02em; }
        .page-kicker { color: var(--amber); font-size: .76rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
        .page-title { color: var(--navy); font-size: 2.05rem; font-weight: 750; line-height: 1.2; margin: .15rem 0 .35rem; }
        .page-subtitle { color: var(--muted); margin-bottom: 1.4rem; }
        .brand-mark { font-size: 1.55rem; font-weight: 800; letter-spacing: .08em; color: #fff; }
        .brand-subtitle { color: #b8c7d6; font-size: .78rem; margin: .25rem 0 1.4rem; }
        .status-pill { display: inline-block; border-radius: 999px; padding: .25rem .62rem; font-size: .74rem; font-weight: 650; margin: .12rem .15rem .12rem 0; }
        .status-ok { background: #d9f2e2; color: #1d6337; }
        .status-warn { background: #fff2cc; color: #8a5a00; }
        .status-neutral { background: #e6eef5; color: #486581; }
        .metric-card { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem; min-height: 108px; box-shadow: 0 2px 10px rgba(16,42,67,.04); }
        .metric-label { color: var(--muted); font-size: .78rem; }
        .metric-value { color: var(--navy); font-size: 1.65rem; font-weight: 760; margin-top: .25rem; }
        .metric-note { color: var(--muted); font-size: .75rem; margin-top: .22rem; }
        .feature-card { background: #fff; border: 1px solid var(--line); border-left: 4px solid var(--amber); border-radius: 10px; padding: 1rem 1.1rem; min-height: 118px; }
        .feature-title { color: var(--navy); font-weight: 720; margin-bottom: .35rem; }
        .feature-text { color: var(--muted); font-size: .88rem; line-height: 1.55; }
        .evidence-card { border: 1px solid var(--line); border-radius: 9px; padding: .7rem .85rem; background: #fbfcfe; margin: .35rem 0; }
        .evidence-source { color: var(--navy); font-weight: 700; font-size: .82rem; }
        .evidence-text { color: #52606d; font-size: .82rem; line-height: 1.5; margin-top: .25rem; }
        .section-label { color: var(--navy); font-size: .95rem; font-weight: 720; margin: .8rem 0 .45rem; }
        .stButton button, .stDownloadButton button { border-radius: 8px; font-weight: 650; }
        div[data-testid="stMetric"] { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: .7rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(active: str = "") -> None:
    with st.sidebar:
        st.markdown('<div class="brand-mark">工程项目RAG智能问答系统</div>', unsafe_allow_html=True)
        st.markdown('<div class="brand-subtitle">工程资料 · 图纸 · 规范智能查询平台</div>', unsafe_allow_html=True)
        st.markdown('<span class="status-pill status-ok">● 本地服务</span><span class="status-pill status-neutral">Ollama</span>', unsafe_allow_html=True)
        st.divider()
        st.caption("项目工作台")
        st.page_link("app.py", label="项目总览", icon="🏠")
        st.page_link("pages/1_💬_问答.py", label="智能问答", icon="💬")
        st.page_link("pages/2_📁_知识库管理.py", label="资料库管理", icon="📁")
        st.page_link("pages/3_⚙️_系统设置.py", label="系统设置", icon="⚙️")
        st.page_link("pages/4_🧭_图纸审查.py", label="图纸审查工作流", icon="🧭")
        st.divider()
        st.caption("当前定位")
        st.markdown("监理资料数字化助手  ·  MVP", unsafe_allow_html=True)
        st.caption("建议启动顺序：Ollama → API → 前端")


def page_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="page-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def api_request(method: str, path: str, **kwargs: Any) -> requests.Response | None:
    try:
        return requests.request(method, f"{API_BASE}{path}", **kwargs)
    except requests.RequestException:
        return None


def ollama_status() -> tuple[bool, list[str]]:
    try:
        response = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
        if response.ok:
            models = [item.get("name", "") for item in response.json().get("models", [])]
            return True, models
    except requests.RequestException:
        pass
    return False, []


def render_sources(sources: list[dict], expandable: bool = True) -> None:
    if not sources:
        return
    with st.expander(f"查看引用依据（{len(sources)} 条）") if expandable else st.container():
        for source in sources:
            name = escape(str(source.get("source", "未标注文件")))
            page = escape(str(source.get("page", "-") or "-"))
            content = escape(str(source.get("content", "")))
            st.markdown(
                f'<div class="evidence-card"><div class="evidence-source">{name} · 第 {page} 页</div><div class="evidence-text">{content}</div></div>',
                unsafe_allow_html=True,
            )
