"""仅显式运行时开放历史审查接口，不包含主应用的入库任务。"""
from fastapi import FastAPI
from api.routes.review import router
app = FastAPI(title="历史图纸审查实验")
app.include_router(router, prefix="/api/v1")
