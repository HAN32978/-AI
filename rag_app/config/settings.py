"""
settings.py 配置管理模块 —— 事用Pydantic Settings 实现类型安全的配置。

.env文件只是存储配置的原材料，它本身不会被程序自动识别的，必须有代码显式的读取他。

Pydantic Settings 是一个用于管理应用程序配置的工具，它可以从多种来源加载配置，包括环境变量、命令行参数、.env文件等。
它还可以自动验证配置的类型和格式，并提供默认值和环境变量名称的映射。

最简单的理解，不设置的话，你需要再所有需要加载环境变量的文件中写代码，一处修改处处修改，很麻烦。
"""
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    配置管理类
    """
    model_config = SettingsConfigDict(
        env_file=Path(__file__).with_name(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 项目基本配置
    PROJECT_NAME: str = "工程项目RAG智能问答系统"
    PROJECT_VERSION: str = "1.0.0"
    BASE_DIR : Path = Path(__file__).parent.parent.resolve()

    # 数据目录
    DATA_DIR: Path = BASE_DIR / "data"
    VECTOR_DB_DIR : Path = BASE_DIR / "vector_db"
    MODELS_DIR : Path = BASE_DIR / "models"
    UPLOAD_DIR : Path = BASE_DIR / "upload"

    # 向量库配置
    VECTOR_STORE_TYPE : Literal["faiss", "chroma"] = "chroma"
    EMBEDDING_MODEL_NAME : str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DEVICE : str = "cpu"      # 可以配置cuda
    CHUNK_SIZE : int = 500
    CHUNK_OVERLAP : int = 50

    # 检索配置
    SEARCH_TOP_K : int = 5
    USE_RERANKER : bool = False
    RERANKER_MODEL_NAME : str = "BAAI/bge-reranker-base"

    # LLM配置
    LLM_PROVIDER : Literal[
        "ollama", "openai", "deepseek", "siliconflow", "dashscope",
        "zhipu", "moonshot", "minimax", "hunyuan", "custom",
    ] = "ollama"

    # ollama配置
    OLLAMA_BASE_URL : str = "http://localhost:11434"
    OLLAMA_MODEL_NAME : str = "qwen2.5:0.5b"

    # OpenAI配置
    OPENAI_API_KEY : str = ""
    OPENAI_BASE_URL : str = "https://api.openai.com/v1"
    OPENAI_MODEL_NAME : str = "gpt-3.5-turbo"

    # DeepSeek OpenAI 兼容接口
    DEEPSEEK_API_KEY : str = ""
    DEEPSEEK_BASE_URL : str = "https://api.deepseek.com"
    DEEPSEEK_MODEL_NAME : str = "deepseek-flash"

    # SiliconFlow配置
    # 密钥只从 config/.env 或系统环境变量读取，避免误提交到代码仓库。
    SILICONFLOW_API_KEY : str = ""
    SILICONFLOW_BASE_URL : str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_MODEL_NAME : str = "Qwen/Qwen2.5-7B-Instruct"

    # 阿里云百炼（DashScope）OpenAI 兼容接口
    DASHSCOPE_API_KEY : str = ""
    DASHSCOPE_BASE_URL : str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_MODEL_NAME : str = "qwen-plus"

    # 其他常用国内 OpenAI 兼容接口
    ZHIPU_API_KEY : str = ""
    ZHIPU_BASE_URL : str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_MODEL_NAME : str = "glm-4-flash"

    MOONSHOT_API_KEY : str = ""
    MOONSHOT_BASE_URL : str = "https://api.moonshot.cn/v1"
    MOONSHOT_MODEL_NAME : str = "moonshot-v1-8k"

    MINIMAX_API_KEY : str = ""
    MINIMAX_BASE_URL : str = "https://api.minimaxi.com/v1"
    MINIMAX_MODEL_NAME : str = "MiniMax-M3"

    HUNYUAN_API_KEY : str = ""
    HUNYUAN_BASE_URL : str = "https://api.hunyuan.cloud.tencent.com/v1"
    HUNYUAN_MODEL_NAME : str = "hunyuan-turbos-latest"

    # 任何其他 OpenAI 兼容网关（例如企业内网代理）
    CUSTOM_API_KEY : str = ""
    CUSTOM_BASE_URL : str = ""
    CUSTOM_MODEL_NAME : str = ""

    # 服务配置
    API_HOST : str = "localhost"
    API_PORT : int = 8000
    STREAMLIT_PORT : int = 8501

    # 日志配置
    LOG_LEVEL : str = "INFO"
    LOG_FILE : Path = BASE_DIR / "app.log"

    # 安全配置
    # ALLOWED_ORIGINS : list[str] = ["*"]       # * 是允许所有的
    ALLOWED_ORIGINS : list[str] = ["http://localhost:8501"]
    SECRET_KEY : str = "your-secret-key"

# 实例化全局配置
settings = Settings()

# 确保必要目录存在
for dir_path in [settings.DATA_DIR, settings.VECTOR_DB_DIR, settings.MODELS_DIR, settings.UPLOAD_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
