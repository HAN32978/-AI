"""按结构化条件查询完整记录，不由语义 top-k 决定总数。"""
import streamlit as st
from ui import (api_request, inject_styles, render_sidebar, page_header, project_selector,
                require_response, document_choices, document_label)

st.set_page_config(page_title="完整记录查询", page_icon="📋", layout="wide")
inject_styles()
render_sidebar("完整记录查询")
page_header("COMPLETE RECORDS", "完整记录查询", "查询 Excel 原表的全部匹配行，保留文件、版本、工作表和行号")
project = project_selector()
docs = {d["id"]: d for d in document_choices(project) if d["record_count"]}
selected = st.selectbox("文档范围", [""] + list(docs), format_func=lambda v: "所有当前版本" if not v else document_label(docs[v]))
cols = st.columns(3)
date = cols[0].text_input("日期（可空）", placeholder="9月9日 / 2026-09-09")
state = cols[1].text_input("原表状态（可空；未登记填 unknown）")
keyword = cols[2].text_input("原表关键词（可空）")
date_review = st.checkbox("只查看日期待核对行（忽略日期筛选，不隐藏未识别记录）")
cols = st.columns(2)
size = cols[0].selectbox("每页记录数", [20, 50, 100, 200])
page = cols[1].number_input("页码", min_value=1, value=1, step=1)
params = {"project_id": project, "page": page, "page_size": size}
if date_review:
    params["date_quality_filter"] = "needs_review"
for key, value in [("document_id", selected), ("date", date if not date_review else ""), ("reported_status", state), ("keyword", keyword)]:
    if value:
        params[key] = value
data = require_response(api_request("GET", "/records", params=params, timeout=15))
if data:
    st.metric("全部匹配记录", data["total"])
    st.caption(f"第 {page} 页 / 共 {max(1, (data['total'] + size - 1) // size)} 页 · 本页 {len(data['items'])} 条")
    st.info(data["note"])
    st.caption(f"当前范围日期待核对：{data['unresolved_date_count']} 行；未识别/缺少日：{data['unrecognized_date_count']} 行。年份分布：{data['year_distribution']}")
    rows = data["items"]
    st.dataframe([{"文件": r["original_filename"], "版本": r["version_label"], "日期": r["business_date"] or r["date_raw"] or "未登记",
                   "部位": r["location"], "问题原文": r["issue_text"], "整改要求": r["requirement"],
                   "原表状态": r["reported_status"] or "未登记", "工作表": r["sheet_name"], "行号": r["row_number"],
                   "日期识别": r["date_quality"], "日期说明": r["date_error"]} for r in rows],
                 use_container_width=True, hide_index=True)
    if st.button("生成完整筛选清单 CSV"):
        export_params = {k: v for k, v in params.items() if k not in {"page", "page_size"}}
        response = api_request("GET", "/records/export", params=export_params, timeout=30)
        if response is not None and response.ok:
            st.download_button("下载全部匹配记录 CSV", response.content, "完整记录清单.csv", "text/csv")
        else:
            st.error("导出失败。")
    if rows:
        lookup = {r["id"]: r for r in rows}
        record_id = st.selectbox("查看原表字段 / 登记整改事项", list(lookup),
                                 format_func=lambda v: f"{lookup[v]['original_filename']} · {lookup[v]['sheet_name']} 第 {lookup[v]['row_number']} 行")
        record = lookup[record_id]
        st.json(record["cells"])
        with st.form("register_issue"):
            actor = st.text_input("登记人")
            description = st.text_area("问题描述（可补充，来源行继续保留）", value=record["issue_text"] or "")
            responsible = st.text_input("责任单位/责任人", value=record["responsible_party"] or "")
            if st.form_submit_button("登记到现场整改闭环"):
                result = require_response(api_request("POST", "/issues", json={"project_id": project, "record_id": record_id,
                                          "description": description, "actor": actor, "responsible_party": responsible}, timeout=10))
                if result:
                    st.success("整改事项已登记（重复登记返回已有事项），请到现场整改页面处理。")
