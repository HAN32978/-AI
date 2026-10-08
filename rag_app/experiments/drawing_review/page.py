"""Join the upstream CAD finding export with local RAG source retrieval."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "frontend"))

import streamlit as st

from ui import api_request, inject_styles, page_header, render_sidebar, render_sources


st.set_page_config(page_title="图纸审查工作流 | 工程项目RAG智能问答系统", page_icon="🧭", layout="wide")
inject_styles()
st.warning("历史实验模块，已移出主产品；不作为现场整改业务流程。需单独启动历史 API。")
page_header("DRAWING REVIEW", "图纸审查工作流", "导入图纸审查问题，检索工程资料中的候选依据，逐项人工复核")

st.info("先在上游审图模块导出问题池 JSON。候选资料仅供复核，系统不自动确认规范适用性或图纸合规性。")
uploaded = st.file_uploader("审查问题池 JSON", type=["json"], help="支持上游 ProblemPool.to_json() 导出的 issues 数组")
project_name = st.text_input("项目名称", value="演示项目", max_chars=100)
top_k = st.slider("每条问题检索候选片段", min_value=1, max_value=10, value=3)

if st.button("检索候选依据", type="primary"):
    if uploaded is None:
        st.warning("请先选择问题池 JSON 文件。")
    elif uploaded.size > 5 * 1024 * 1024:
        st.error("JSON 文件不能超过 5 MB。")
    else:
        try:
            payload = json.loads(uploaded.getvalue().decode("utf-8-sig"))
            issues = payload.get("issues") if isinstance(payload, dict) else None
            if not isinstance(issues, list) or not issues:
                raise ValueError("文件需要包含非空 issues 数组。")
            response = api_request(
                "POST", "/review/evidence",
                json={"project_name": project_name, "issues": issues, "top_k": top_k},
                timeout=120,
            )
            if response is None:
                st.error("无法连接 RAG API，请先启动后端。")
            elif not response.ok:
                st.error(f"检索失败（HTTP {response.status_code}）：{response.text[:400]}")
            else:
                st.session_state.review_result = response.json()
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            st.error(f"问题池文件无效：{exc}")

result = st.session_state.get("review_result")
if result:
    summary = result["summary"]
    a, b, c = st.columns(3)
    a.metric("审查问题", summary["total"])
    b.metric("缺少候选依据", summary["missing_sources"])
    c.metric("A级待复核", summary["high_risk"])
    st.caption("工作流：" + " → ".join(result["workflow"]))
    for issue in result["issues"]:
        with st.expander(f"{issue['issue_id']} · {issue['status']} · {issue['description'][:50]}"):
            st.write(f"图纸：{issue['drawing_name'] or '未标注'} ｜ 位置：{issue['location'] or '未标注'} ｜ 专业：{issue['professional'] or '未标注'}")
            st.write(issue["description"])
            if issue["standard_code_from_audit"]:
                st.caption(f"审图模块给出的待核查条款：{issue['standard_code_from_audit']} {issue['standard_clause_from_audit']}")
            if issue["candidate_sources"]:
                render_sources(issue["candidate_sources"], expandable=False)
            else:
                st.warning("知识库未返回候选资料。先补充对应工程资料或规范版本，再由专业人员核查。")
            st.caption(issue["review_note"])
    st.download_button(
        "下载待复核结果 JSON",
        data=json.dumps(result, ensure_ascii=False, indent=2),
        file_name="工程图纸_候选依据待复核.json", mime="application/json",
    )
