# 工程图纸智能审查与 RAG 项目

本仓库正在将开源工程图纸审查系统与已有的 Windows 本地 LangChain + RAG 智能客服项目整合，目标是形成可演示的施工/监理场景应用。

## 当前进度

- 已导入 [AI-CAD-Audit-System](https://github.com/2sellyogurt/AI-CAD-Audit-System) 的 `main` 代码，位于 [upstream/](upstream/)。
- 导入基于上游 Git tree `c5234607ae76309c709678b0f209bd892e28b937`；上游代码采用 MIT License，原许可证保留在 [upstream/LICENSE](upstream/LICENSE)。
- 已导入 [cad-spatial-analysis](https://github.com/YK999671/cad-spatial-analysis) 的代码，位于 [cad-spatial-analysis/](cad-spatial-analysis/)；来源为上游提交 `66d65aa9586c567fe00fd4e1f674c8c0e5d3ae2f`，MIT 许可证保留在 [cad-spatial-analysis/LICENSE](cad-spatial-analysis/LICENSE)。
- LangChain + RAG 智能客服尚未导入：需要用户提供 Windows 项目代码或仓库地址后，才能进行接口适配和端到端验证。

## 运行上游演示

需要 Python 3.10+；在 Windows PowerShell 中：

```powershell
cd upstream
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python v7/master_v7.py --demo
```

演示模式使用模拟数据。图纸审查结果仍须人工复核；接入真实规范、图纸和模型后再评估业务准确率。更多运行说明见 [上游 README](upstream/README.md)。

## 下一步

见 [集成方案](docs/INTEGRATION.md)。请提供 Windows 本地 RAG 项目的 GitHub 链接，或打包上传其源代码（排除 `.env`、密钥、客户资料和向量库原始数据）。
