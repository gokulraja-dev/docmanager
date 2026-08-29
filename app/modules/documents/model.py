from sqlalchemy import String, DateTime, func, Index, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid
from app.db.base import Base

# Document model representing a document entity in the database
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    search_text: Mapped[str] = mapped_column(TSVECTOR, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

# Search Index
Index("idx_documents_search", Document.search_text, postgresql_using="gin")

# DocumentNode model representing hierarchical structure of document nodes
class DocumentNode(Base):
    __tablename__ = "document_nodes"

    node_id: Mapped[str] = mapped_column(String(26), primary_key=True)  # ULID / KSUID
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    parent_node_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)