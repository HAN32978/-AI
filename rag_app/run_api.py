#!/usr/bin/env python
"""
API服务启动脚本
"""
import uvicorn
from config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        # 作品集/本地演示模式使用单进程，避免 Windows reloader 留下旧配置子进程。
        reload=False,
        log_level=settings.LOG_LEVEL.lower()
    )
