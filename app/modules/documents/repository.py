from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from .model import Document, DocumentNode

# Method to create a new document
async def create_document(db: AsyncSession, title: str, description: str | None = None, document_type: str | None = None):
    document = Document(title=title, description=description, document_type=document_type)
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document

# Method to get a document by id
async def get_document_by_id(db: AsyncSession, document_id: str):
    stmt = select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    return await db.scalar(stmt)

# Method to get node by id
async def get_node_by_id(db: AsyncSession, node_id: str):
    stmt = select(DocumentNode).where(DocumentNode.node_id == node_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

# Method to create new node record
async def create_node_record(db: AsyncSession, node_id: str, document_id: str, parent_node_id: str, path: str):
    node = DocumentNode(node_id=node_id, document_id=document_id, parent_node_id=parent_node_id, path=path)
    db.add(node)
    await db.commit()
    await db.flush()
    await db.refresh(node)
    return node

# Method to get node with document
async def get_node_with_document(db, node_id: str):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.node_id == node_id,
            DocumentNode.deleted_at.is_(None)
        )
    )
    result = await db.execute(stmt)
    return result.first()


# Method to get immediate children
async def get_immediate_children(db, parent_node_id: str):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.parent_node_id == parent_node_id,
            DocumentNode.deleted_at.is_(None)
        )
        .order_by(DocumentNode.path)
    )
    result = await db.execute(stmt)
    return result.all()

# Method to get subtree
async def get_subtree_nodes(db, path: str):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.path.startswith(path),
            DocumentNode.deleted_at.is_(None)
        )
        .order_by(DocumentNode.path)
    )
    result = await db.execute(stmt)
    return result.all()

# Method to get node
async def get_node(db, node_id: str):
    stmt = (
        select(DocumentNode)
        .where(
            DocumentNode.node_id == node_id,
            DocumentNode.deleted_at.is_(None)
        )
    )
    return await db.scalar(stmt)

# Method to update document
async def update_document(db: AsyncSession, document, title: str | None = None, description: str | None = None, document_type: str | None = None):
    if title is not None:
        document.title = title
    if description is not None:
        document.description = description
    if document_type is not None:
        document.document_type = document_type
    await db.commit()
    await db.refresh(document)
    return document

# Method to soft delete a node record and a document
async def soft_delete_node_record(db: AsyncSession, path: str):
    now = func.now()

    # Delete node
    await db.execute(
        update(DocumentNode)
        .where(
            DocumentNode.path.startswith(path),
            DocumentNode.deleted_at.is_(None)
        )
        .values(deleted_at=now)
    )

    # Delete document linked to those nodes
    await db.execute(
        update(Document)
        .where(
            Document.id.in_(
                select(DocumentNode.document_id)
                .where(
                    DocumentNode.path.startswith(path),
                )
            )
        )
        .values(deleted_at=now)
    )

    await db.commit()
