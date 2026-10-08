"""统一封装本地 Ollama 和 OpenAI 兼容云端模型服务。"""

import logging
import requests

from langchain_community.chat_models import ChatOllama
from langchain_openai import ChatOpenAI

from config.settings import settings


logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    """模型服务不可用，向界面提供可操作的错误信息。"""


def ensure_llm_ready() -> None:
    """Ollama 客户端初始化不代表指定模型已经安装。"""
    if settings.LLM_PROVIDER != "ollama":
        return
    try:
        response = requests.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
    except (requests.RequestException, ValueError) as exc:
        raise LLMServiceError("无法连接本地 Ollama 服务，请先启动 Ollama，再检查系统设置中的服务地址。") from exc
    model = settings.OLLAMA_MODEL_NAME
    expected = model if ":" in model else model + ":latest"
    if model not in names and expected not in names:
        raise LLMServiceError(f"本地模型 {model} 尚未安装。请在终端运行 ollama pull {model}，下载完成后重新提问。")


class LLMClient:
    def __init__(self):
        self._llm = None
        self._initialize_client()

    def _initialize_client(self):
        """初始化大模型客户端。"""
        try:
            if settings.LLM_PROVIDER == "ollama":
                self._llm = ChatOllama(
                    model=settings.OLLAMA_MODEL_NAME,
                    base_url=settings.OLLAMA_BASE_URL,
                    temperature=0.1,
                    verbose=True,
                )
                logger.info(
                    "Ollama 客户端已初始化：%s",
                    settings.OLLAMA_MODEL_NAME,
                )
            else:
                providers = {
                    "openai": {
                        "api_key": settings.OPENAI_API_KEY,
                        "base_url": settings.OPENAI_BASE_URL,
                        "model": settings.OPENAI_MODEL_NAME,
                        "label": "OpenAI",
                    },
                    "deepseek": {
                        "api_key": settings.DEEPSEEK_API_KEY,
                        "base_url": settings.DEEPSEEK_BASE_URL,
                        "model": settings.DEEPSEEK_MODEL_NAME,
                        "label": "DeepSeek",
                    },
                    "siliconflow": {
                        "api_key": settings.SILICONFLOW_API_KEY,
                        "base_url": settings.SILICONFLOW_BASE_URL,
                        "model": settings.SILICONFLOW_MODEL_NAME,
                        "label": "SiliconFlow",
                    },
                    "dashscope": {
                        "api_key": settings.DASHSCOPE_API_KEY,
                        "base_url": settings.DASHSCOPE_BASE_URL,
                        "model": settings.DASHSCOPE_MODEL_NAME,
                        "label": "阿里云百炼",
                    },
                    "zhipu": {
                        "api_key": settings.ZHIPU_API_KEY,
                        "base_url": settings.ZHIPU_BASE_URL,
                        "model": settings.ZHIPU_MODEL_NAME,
                        "label": "智谱 AI",
                    },
                    "moonshot": {
                        "api_key": settings.MOONSHOT_API_KEY,
                        "base_url": settings.MOONSHOT_BASE_URL,
                        "model": settings.MOONSHOT_MODEL_NAME,
                        "label": "Moonshot / Kimi",
                    },
                    "minimax": {
                        "api_key": settings.MINIMAX_API_KEY,
                        "base_url": settings.MINIMAX_BASE_URL,
                        "model": settings.MINIMAX_MODEL_NAME,
                        "label": "MiniMax",
                    },
                    "hunyuan": {
                        "api_key": settings.HUNYUAN_API_KEY,
                        "base_url": settings.HUNYUAN_BASE_URL,
                        "model": settings.HUNYUAN_MODEL_NAME,
                        "label": "腾讯混元",
                    },
                    "custom": {
                        "api_key": settings.CUSTOM_API_KEY,
                        "base_url": settings.CUSTOM_BASE_URL,
                        "model": settings.CUSTOM_MODEL_NAME,
                        "label": "自定义 OpenAI 兼容接口",
                    },
                }
                provider = providers.get(settings.LLM_PROVIDER)
                if provider is None:
                    raise ValueError(f"不支持的大模型供应商：{settings.LLM_PROVIDER}")
                if not provider["api_key"]:
                    raise ValueError(
                        f"{provider['label']} 未配置 API Key，请在 config/.env 中填写对应密钥"
                    )
                if not provider["base_url"] or not provider["model"]:
                    raise ValueError(
                        f"{provider['label']} 缺少 Base URL 或模型名，请在 config/.env 中补齐"
                    )
                self._llm = ChatOpenAI(
                    model=provider["model"],
                    api_key=provider["api_key"],
                    base_url=provider["base_url"],
                    temperature=0.1,
                    verbose=True,
                )
                logger.info(
                    "%s 客户端已初始化：%s (%s)",
                    provider["label"],
                    provider["model"],
                    provider["base_url"],
                )

        except Exception:
            logger.exception("初始化大模型客户端失败")
            raise

    def get_llm(self):
        """返回大模型实例。"""
        return self._llm

    def change_provider(self, provider: str, **kwargs):
        """切换大模型供应商。"""
        settings.LLM_PROVIDER = provider

        for key, value in kwargs.items():
            setattr(settings, key, value)

        self._initialize_client()
        logger.info("大模型供应商已切换为：%s", provider)



_llm_client = None


def get_llm():
    """获取全局大模型实例。"""
    global _llm_client

    if _llm_client is None:
        _llm_client = LLMClient()

    return _llm_client.get_llm()
