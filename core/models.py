import uuid
from datetime import datetime

from sqlalchemy import Column, Index, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from core.db import Base

# Vai tro nguoi dung (luu dang chuoi de don gian hoa, khong dung SQLAlchemy Enum)
ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"

# Trang thai tai lieu
DOC_STATUS_PENDING = "pending"
DOC_STATUS_INDEXED = "indexed"
DOC_STATUS_FAILED = "failed"

# Vong doi phien ban tai lieu. Chi tai lieu ACTIVE duoc dua vao kho truy xuat.
DOC_LIFECYCLE_DRAFT = "draft"
DOC_LIFECYCLE_ACTIVE = "active"
DOC_LIFECYCLE_SUPERSEDED = "superseded"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(20), default=ROLE_STUDENT, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="uploader")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), default="Cuộc trò chuyện mới", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)  # JSON-encoded string
    message_metadata = Column("metadata", Text, nullable=True)  # JSON-encoded message metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("uq_documents_content_hash", "content_hash", unique=True),
        UniqueConstraint("document_code", "version_number", name="uq_documents_code_version"),
    )

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    path = Column(String(500), nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default=DOC_STATUS_PENDING, nullable=False)
    content_hash = Column(String(64), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    document_code = Column(String(100), nullable=False, index=True)
    version_number = Column(Integer, default=1, nullable=False)
    lifecycle_status = Column(String(20), default=DOC_LIFECYCLE_DRAFT, nullable=False, index=True)
    replaces_document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    uploader = relationship("User", back_populates="documents")
