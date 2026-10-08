"""多轮对话记忆管理模块。"""

import logging
import uuid
from datetime import datetime, timedelta

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

logger = logging.getLogger(__name__)


class ConversationSession:
    """单个会话的消息历史。"""

    def __init__(self, session_id: str, window_size: int = 5):
        self.session_id = session_id
        self.window_size = window_size
        self.created_at = datetime.now()
        self.last_active = self.created_at
        self.history = InMemoryChatMessageHistory()
        self.metadata: dict = {}

    def add_user_message(self, message: str) -> None:
        self.history.add_message(HumanMessage(content=message))
        self.last_active = datetime.now()

    def add_ai_message(self, message: str) -> None:
        self.history.add_message(AIMessage(content=message))
        self.last_active = datetime.now()

    def get_memory(self) -> list[BaseMessage]:
        return self.history.messages[-self.window_size * 2 :]

    def clear(self) -> None:
        self.history.clear()
        self.last_active = datetime.now()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "messages": [
                {"role": message.type, "content": message.content}
                for message in self.history.messages
            ],
            "metadata": self.metadata,
        }


class MemoryManger:
    """多轮对话记忆管理器，保留原项目类名以兼容现有导入。"""

    def __init__(self, window_size: int = 5, session_ttl_minutes: int = 60):
        self.sessions: dict[str, ConversationSession] = {}
        self.session = self.sessions
        self.window_size = window_size
        self.session_ttl = timedelta(minutes=session_ttl_minutes)

    def create_session(self, session_id: str | None = None) -> str:
        session_id = session_id or str(uuid.uuid4())
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationSession(session_id, self.window_size)
            logger.info("创建新对话: %s", session_id)
        return session_id

    def get_session(self, session_id: str) -> ConversationSession | None:
        session = self.sessions.get(session_id)
        if session:
            session.last_active = datetime.now()
        return session

    get_sesson = get_session

    def get_or_create_session(self, session_id: str | None = None) -> ConversationSession:
        session_id = session_id or "default"
        self.create_session(session_id)
        return self.sessions[session_id]

    def add_exchange(self, session_id: str, question: str, answer: str) -> None:
        session = self.get_or_create_session(session_id)
        session.add_user_message(question)
        session.add_ai_message(answer)

    def get_chat_history(self, session_id: str) -> list[BaseMessage]:
        return self.get_or_create_session(session_id).get_memory()

    def clear_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        if session:
            session.clear()

    def delete_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def cleanup_old_sessions(self) -> int:
        now = datetime.now()
        expired = [
            session_id
            for session_id, session in self.sessions.items()
            if now - session.last_active > self.session_ttl
        ]
        for session_id in expired:
            self.delete_session(session_id)
        return len(expired)

    def list_sessions(self) -> list[dict]:
        return [session.to_dict() for session in self.sessions.values()]

    def get_default_memory(self) -> list[BaseMessage]:
        return self.get_chat_history("default")


_memory_manager_instance: MemoryManger | None = None


def get_memory_manager() -> MemoryManger:
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManger()
    return _memory_manager_instance
