"""人工整改回复、复查与销项；AI 不改变业务状态。"""
import streamlit as st
from ui import (api_request, inject_styles, render_sidebar, page_header, project_selector,
                require_response, document_choices, document_label, ISSUE_STATES)

st.set_page_config(page_title="现场整改资料闭环", page_icon="🛠️", layout="wide")
inject_styles()
render_sidebar("现场整改资料闭环")
page_header("RECTIFICATION TRACKING", "现场整改资料闭环", "问题登记 → 整改回复 → 申请复查 → 人工复查与销项")
project = project_selector()
st.info("照片、回复文件和模型回答不会自动销项。整改回复与复查通过需登记操作人、说明，并关联本项目已归档依据。")
st.caption("当前为本地单用户演示，操作人由人工填写；未实施账号认证或电子签章。")
with st.expander("新建现场问题（Excel 来源问题可在记录查询中登记）"):
    with st.form("create_site_issue"):
        description = st.text_area("问题描述")
        location = st.text_input("现场部位")
        responsible = st.text_input("责任单位/责任人")
        actor = st.text_input("登记人")
        if st.form_submit_button("登记问题"):
            result = require_response(api_request("POST", "/issues", json={"project_id": project, "description": description,
                                      "location": location, "responsible_party": responsible, "actor": actor}, timeout=10))
            if result:
                st.success("问题已登记，状态为待整改回复。")

status = st.selectbox("闭环状态", [""] + list(ISSUE_STATES), format_func=lambda v: "全部状态" if not v else ISSUE_STATES[v])
if st.button("刷新整改事项"):
    st.rerun()
data = require_response(api_request("GET", "/issues", params={"project_id": project, **({"status": status} if status else {})}, timeout=10))
items = data["items"] if data else []
if not items:
    st.info("暂无符合条件的整改事项。")
else:
    st.dataframe([{"问题": i["description"], "部位": i["location"], "责任方": i["responsible_party"], "状态": ISSUE_STATES[i["status"]],
                   "登记人": i["created_by"], "更新时间": i["updated_at"]} for i in items], use_container_width=True, hide_index=True)
    lookup = {i["id"]: i for i in items}
    selected = st.selectbox("处理事项", list(lookup), format_func=lambda v: f"{ISSUE_STATES[lookup[v]['status']]} · {lookup[v]['location']} · {lookup[v]['description'][:70]}")
    issue = require_response(api_request("GET", f"/issues/{selected}", params={"project_id": project}, timeout=10))
    if issue:
        st.subheader(ISSUE_STATES[issue["status"]])
        st.write(issue["description"])
        if issue.get("source_record"):
            source = issue["source_record"]
            st.caption(f"来源：{source['original_filename']} · {source['version_label']} · {source['sheet_name']} 第 {source['row_number']} 行")
            with st.expander("原表字段"):
                st.json(source["cells"])
        docs = {d["id"]: d for d in document_choices(project) if d["status"] in {"ready", "partial", "stored_only"}}
        actions = {"open": ["reply"], "reopened": ["reply"], "reply_received": ["reply", "request_recheck"],
                   "recheck_pending": ["recheck_pass", "recheck_fail"], "closed": ["reopen"]}[issue["status"]]
        labels = {"reply": "登记整改回复", "request_recheck": "申请人工复查", "recheck_pass": "人工复查通过并销项",
                  "recheck_fail": "人工复查不通过，退回整改", "reopen": "重新打开事项"}
        with st.form(f"event_{selected}_{issue['status']}"):
            action = st.selectbox("处理操作", actions, format_func=labels.get)
            actor = st.text_input("本次操作人")
            note = st.text_area("整改回复 / 复查结论及依据说明")
            attachments = st.multiselect("关联依据文件（先到资料库上传）", list(docs), format_func=lambda v: document_label(docs[v]))
            confirm = st.checkbox("已人工核实本次说明与关联依据")
            submitted = st.form_submit_button("保存人工处理记录", type="primary")
        if submitted:
            if not confirm:
                st.warning("请完成人工核实后勾选确认。")
            else:
                result = require_response(api_request("POST", f"/issues/{selected}/events", json={"project_id": project,
                                          "action": action, "actor": actor, "note": note, "attachment_ids": attachments}, timeout=15))
                if result:
                    st.success(f"已保存，当前状态：{ISSUE_STATES[result['status']]}。请刷新查看。")
                    issue = result
        st.subheader("处理记录与依据")
        for event in issue["events"]:
            with st.expander(f"{event['created_at']} · {event['actor']} · {labels.get(event['action'], '登记问题')}"):
                st.write(event["note"])
                for doc_id in event["attachment_ids"]:
                    st.write(document_label(docs[doc_id]) if doc_id in docs else f"文档 ID：{doc_id}")
        draft = f"# 现场整改事项记录（人工复核稿）\n\n事项 ID：{selected}\n\n问题：{issue['description']}\n\n部位：{issue['location']}\n\n责任方：{issue['responsible_party']}\n\n当前状态：{ISSUE_STATES[issue['status']]}\n\n"
        for event in issue["events"]:
            draft += f"## {event['created_at']} {event['actor']} {labels.get(event['action'], '登记问题')}\n\n{event['note']}\n\n依据文件 ID：{', '.join(event['attachment_ids']) or '无'}\n\n"
        st.download_button("导出整改事项记录 MD", draft, f"整改事项_{selected[:8]}.md", "text/markdown")
