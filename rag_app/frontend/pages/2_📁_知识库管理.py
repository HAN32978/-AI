"""原件台账与持久化入库状态。"""
import streamlit as st
from ui import (api_request, inject_styles, render_sidebar, page_header, project_selector,
                require_response, document_choices, document_label, DOCUMENT_STATES)

st.set_page_config(page_title="资料库管理", page_icon="📁", layout="wide")
inject_styles()
render_sidebar("资料库管理")
page_header("DOCUMENT REGISTRY", "资料库管理", "接收原件、登记版本和业务日期，查看真实解析与索引进度")
project = project_selector()
with st.expander("新建项目"):
    with st.form("new_project"):
        name = st.text_input("项目名称")
        if st.form_submit_button("创建项目"):
            data = require_response(api_request("POST", "/projects", json={"name": name}, timeout=10))
            if data:
                st.success("项目已创建，请在当前项目中选择。")

docs = document_choices(project)
by_id = {d["id"]: d for d in docs}
upload_tab, registry_tab = st.tabs(["上传文档", "文档台账与任务"])
with upload_tab:
    st.info("DWG/RVT/IFC 首期接收原件；DWG 可另传 DXF/PDF，RVT 可另传 IFC/PDF 并关联原件。DXF 仅解析可直接读取的文字/属性。扫描 PDF 暂无 OCR。")
    st.caption("DOCX、Excel、TXT、Markdown、文字 PDF 可检索；现场图片可作为整改依据。单文件上限 50MB。")
    with st.form("upload_documents", clear_on_submit=False):
        files = st.file_uploader("选择文件（可多选）", type=["pdf", "docx", "doc", "xlsx", "xls", "txt", "md", "dwg", "dxf", "rvt", "ifc", "png", "jpg", "jpeg"], accept_multiple_files=True)
        category = st.selectbox("文档分类", ["general", "检查记录", "整改回复", "复查依据", "管理制度", "技术文档", "图纸原件", "培训材料"])
        date = st.text_input("业务日期（可空；有年份请填 YYYY-MM-DD）", placeholder="2026-09-09 或 9月9日")
        number = st.text_input("文档编号（可空）")
        version = st.text_input("版本标签（可空，默认登记时间）", placeholder="V1 / 2026版")
        parent = st.selectbox("关联原件（导出件可选择 DWG/RVT 等）", [""] + list(by_id),
                              format_func=lambda v: "无关联" if not v else document_label(by_id[v]))
        submit = st.form_submit_button("提交入库", type="primary")
    if submit:
        if not files:
            st.warning("请选择文件。")
        for file in files:
            response = api_request("POST", "/upload/file", files={"file": (file.name, file.getvalue())},
                                   data={"project_id": project, "category": category, "business_date": date,
                                         "document_number": number, "version_label": version,
                                         "source_document_id": parent}, timeout=60)
            data = require_response(response)
            if data:
                st.success(f"{file.name}：{data['message']}（{DOCUMENT_STATES.get(data['status'], data['status'])}）")
        st.caption("已接收不代表可检索。请在文档台账中刷新，确认状态为可检索/部分解析后查询内容。")

with registry_tab:
    if st.button("刷新台账与入库进度"):
        st.rerun()
    stats = require_response(api_request("GET", "/documents/stats", params={"project_id": project}, timeout=5))
    if stats:
        cols = st.columns(4)
        for col, title, key in zip(cols, ["文档版本总数", "当前文档", "完整表格记录", "当前索引片段"],
                                   ["document_count", "current_document_count", "record_count", "indexed_chunks"]):
            col.metric(title, stats[key])
    if not docs:
        st.info("当前项目暂无文档。历史文件启动后会登记到默认项目，原件继续保留。")
    else:
        st.dataframe([{"文件": d["original_filename"], "分类": d["category"], "版本": d["version_label"],
                       "当前版本": bool(d["is_current"]), "业务日期": d["business_date"] or d["month_day"] or "未登记",
                       "状态": DOCUMENT_STATES.get(d["status"], d["status"]), "记录数": d["record_count"],
                       "索引片段": d["chunk_count"], "说明/错误": d["error"]} for d in docs], use_container_width=True, hide_index=True)
        st.caption("当前版本按同一项目、同名文件分组；明确选择文档可查询历史版本。失败的新版本不会替换旧的可用版本。")
        selected = st.selectbox("查看原件与任务", list(by_id), format_func=lambda v: document_label(by_id[v]))
        detail = require_response(api_request("GET", f"/documents/{selected}", params={"project_id": project}, timeout=5))
        if detail:
            st.write("文档 ID：", selected)
            st.write("关联原件 ID：", detail["source_document_id"] or "无")
            st.dataframe(detail["tasks"], use_container_width=True, hide_index=True)
            if detail["error"]:
                st.warning(detail["error"])
            if st.button("读取原件下载"):
                response = api_request("GET", f"/documents/{selected}/download", params={"project_id": project}, timeout=30)
                if response is not None and response.ok:
                    st.download_button("下载原件", response.content, detail["original_filename"], key=f"download_{selected}")
                else:
                    st.error("原件读取失败。")
            if detail["status"] in {"failed", "partial", "stored_only"} and st.button("重新解析此文档"):
                data = require_response(api_request("POST", f"/documents/{selected}/retry", params={"project_id": project}, timeout=10))
                if data:
                    st.success("已重新排队；请刷新查看结果。")
