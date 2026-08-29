from sqlalchemy import String, DateTime, func, Index, ForeignKey, Text, Integer, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid
from app.db.base import Base

# Document model representing the logical document/container entity
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Reserved for future full-text indexing sourced from content block text - not populated yet
    search_text: Mapped[str] = mapped_column(TSVECTOR, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

# Search Index
Index("idx_documents_search", Document.search_text, postgresql_using="gin")

# DocumentNode model representing hierarchical structure of document nodes.
# Responsible only for tree position (parent/child, materialized path) - no content/asset concerns.
class DocumentNode(Base):
    __tablename__ = "document_nodes"

    node_id: Mapped[str] = mapped_column(String(26), primary_key=True)  # ULID / KSUID
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    parent_node_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

# DocumentContentBlock model representing one dynamic content unit within a document.
# block_type/data are intentionally free-form so new block types never require a schema change.
class DocumentContentBlock(Base):
    __tablename__ = "document_content_blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    block_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

Index("idx_content_blocks_document_position", DocumentContentBlock.document_id, DocumentContentBlock.position)

# DocumentAsset model representing an uploaded file's metadata. The binary itself lives
# in object storage (see app/core/storage) and is addressed here only via storage_key.
class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    # Mapped to the "metadata" column under a different attribute name since
    # SQLAlchemy's DeclarativeBase already reserves the "metadata" attribute.
    meta: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

Index("idx_assets_document", DocumentAsset.document_id)
