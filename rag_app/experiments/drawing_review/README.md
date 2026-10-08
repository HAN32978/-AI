# 历史图纸审查实验

保留旧版源代码供技术对照，不出现在主导航，主 API 不注册 `/review` 接口。
该实验不代表施工单位或监理单位实施设计审查。

如需单独复现实验，在 `rag_app` 目录启动：

```bat
python -m uvicorn experiments.drawing_review.api:app --host 127.0.0.1 --port 18002
set RAG_API_BASE=http://127.0.0.1:18002/api/v1
python -m streamlit run experiments/drawing_review/page.py --server.port 18502
```

历史实验沿用旧向量检索与人工候选依据复核逻辑，不具备主应用新增的项目隔离与文档台账约束。不要把它与主产品的数据流程混用。
