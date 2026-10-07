from .upload import router as upload_router
from .qa import router as qa_router
from .knowledge import router as knowledge_router
from .system import router as system_router
from .review import router as review_router

__all__ = ["upload_router", "qa_router", "knowledge_router", "system_router", "review_router"]
