"""
系统状态API
"""
from fastapi import APIRouter
from config.settings import settings
from core.llm_client import ensure_llm_ready, LLMServiceError

# 必须定义名为 router 的 APIRouter 实例
router = APIRouter(prefix="/system", tags=["系统状态"])


@router.get("/model_status")
def model_status():
    """本地模型检查安装状态；云端只标记配置，不能宣称调用成功。"""
    if settings.LLM_PROVIDER != "ollama":
        return {"status": "configured", "message": "当前使用云端模型，实际调用结果以问答请求为准。"}
    try:
        ensure_llm_ready()
        return {"status": "ready", "message": f"本地模型已安装：{settings.OLLAMA_MODEL_NAME}"}
    except LLMServiceError as exc:
        return {"status": "unavailable", "message": str(exc)}


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION}


@router.get("/config")
async def get_config():
    """获取当前配置（隐藏敏感信息）"""
    provider_config = {
        "ollama": (settings.OLLAMA_MODEL_NAME, settings.OLLAMA_BASE_URL),
        "openai": (settings.OPENAI_MODEL_NAME, settings.OPENAI_BASE_URL),
        "deepseek": (settings.DEEPSEEK_MODEL_NAME, settings.DEEPSEEK_BASE_URL),
        "siliconflow": (settings.SILICONFLOW_MODEL_NAME, settings.SILICONFLOW_BASE_URL),
        "dashscope": (settings.DASHSCOPE_MODEL_NAME, settings.DASHSCOPE_BASE_URL),
        "zhipu": (settings.ZHIPU_MODEL_NAME, settings.ZHIPU_BASE_URL),
        "moonshot": (settings.MOONSHOT_MODEL_NAME, settings.MOONSHOT_BASE_URL),
        "minimax": (settings.MINIMAX_MODEL_NAME, settings.MINIMAX_BASE_URL),
        "hunyuan": (settings.HUNYUAN_MODEL_NAME, settings.HUNYUAN_BASE_URL),
        "custom": (settings.CUSTOM_MODEL_NAME, settings.CUSTOM_BASE_URL),
    }
    llm_model, llm_base_url = provider_config.get(
        settings.LLM_PROVIDER,
        ("—", "—"),
    )
    return {
        "vector_store_type": settings.VECTOR_STORE_TYPE,
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "search_top_k": settings.SEARCH_TOP_K,
    }
