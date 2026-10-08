"""
知识库管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.dependencies import get_vector_store_dep
from core.vector_store import VectorStoreManager

router = APIRouter(prefix="/knowledge", tags=["知识库管理"])


class DeleteRequest(BaseModel):
    source_path: str


@router.get("/stats")
async def get_knowledge_stats(
    vector_store: VectorStoreManager = Depends(get_vector_store_dep)
):
    """
    获取知识库统计信息
    """
    stats = vector_store.get_collection_stats()
    return stats


@router.post("/delete")
async def delete_document(
    request: DeleteRequest,
):
    """
    根据源文件路径删除文档
    """
    raise HTTPException(409, "已启用文档台账，旧版单独删除向量接口已停用，避免与原件及完整记录状态不一致。")


@router.post("/clear")
async def clear_knowledge_base(
):
    """
    清空整个知识库
    """
    raise HTTPException(409, "已启用文档台账，旧版全局清空向量接口已停用。请保留原件与整改依据。")
