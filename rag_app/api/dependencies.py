"""
FastAPI依赖注入模块
"""
from core.vector_store import get_vector_store_manager
from core.rag_chain import get_rag_chain
from core.document_loader import DocumentLoader
from fastapi import HTTPException
from core.llm_client import LLMServiceError


def get_vector_store_dep():
    """获取向量库依赖"""
    return get_vector_store_manager()


def get_rag_chain_dep():
    """获取RAG链依赖"""
    return LazyRAGChain()


class LazyRAGChain:
    """完整记录查询不初始化模型；语义问答时才加载。"""
    def ask(self, question, session_id, document_ids=None):
        try:
            return get_rag_chain().ask(question, session_id, document_ids=document_ids)
        except ValueError as exc:
            raise LLMServiceError("模型配置不完整或无效，请检查后端 config/.env 中的提供商、API Key、地址与模型名称。") from exc

    def clear_session(self, session_id):
        from core.memory_manager import get_memory_manager
        get_memory_manager().clear_session(session_id)

    def get_chat_history(self, session_id):
        from core.memory_manager import get_memory_manager
        return [{"role": "human" if m.type == "human" else "assistant", "content": m.content}
                for m in get_memory_manager().get_chat_history(session_id)]


def get_document_loader_dep():
    """获取文档加载器依赖"""
    return DocumentLoader()
