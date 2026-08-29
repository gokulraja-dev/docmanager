from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.orm import aliased
import uuid
from .model import Document, DocumentNode

# Method to create a new document
async def create_document(db: AsyncSession, title: str, description: str | None = None):
    document = Document(title=title, description=description)
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

# Method to get root nodes (no parent) - used to list top-level documents
async def get_root_nodes(db):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.parent_node_id.is_(None),
            DocumentNode.deleted_at.is_(None)
        )
        .order_by(DocumentNode.path)
    )
    result = await db.execute(stmt)
    return result.all()

# Method to update document
async def update_document(db: AsyncSession, document, title: str | None = None, description: str | None = None):
    if title is not None:
        document.title = title
    if description is not None:
        document.description = description
    await db.commit()
    await db.refresh(document)
    return document

# Method to soft delete a node subtree as one deletion batch. Only nodes that are not
# already deleted are touched, so an independently-deleted descendant keeps its own
# deleted_at/deletion_batch_id from whenever it was originally deleted.
async def soft_delete_subtree(db: AsyncSession, path: str) -> uuid.UUID:
    batch_id = uuid.uuid4()
    now = func.now()

    result = await db.execute(
        update(DocumentNode)
        .where(
            DocumentNode.path.startswith(path),
            DocumentNode.deleted_at.is_(None)
        )
        .values(deleted_at=now, deletion_batch_id=batch_id)
        .returning(DocumentNode.document_id)
    )
    document_ids = [row[0] for row in result.all()]

    if document_ids:
        await db.execute(
            update(Document)
            .where(Document.id.in_(document_ids))
            .values(deleted_at=now)
        )

    await db.commit()
    return batch_id

# Method to restore every node that was deleted together in one batch (or, if the node
# predates batch tracking, just that single node) along with their documents.
async def restore_deletion_batch(db: AsyncSession, node: DocumentNode) -> list:
    if node.deletion_batch_id is not None:
        node_filter = DocumentNode.deletion_batch_id == node.deletion_batch_id
    else:
        node_filter = DocumentNode.node_id == node.node_id

    result = await db.execute(
        update(DocumentNode)
        .where(node_filter)
        .values(deleted_at=None, deletion_batch_id=None)
        .returning(DocumentNode.document_id)
    )
    document_ids = [row[0] for row in result.all()]

    if document_ids:
        await db.execute(
            update(Document)
            .where(Document.id.in_(document_ids))
            .values(deleted_at=None)
        )

    await db.commit()
    return document_ids

# Method to list the "roots" of deleted subtrees: a deleted node whose parent is either
# absent or not itself deleted. Avoids showing every descendant of an already-listed subtree.
async def get_trash_root_nodes(db: AsyncSession):
    parent = aliased(DocumentNode)

    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .outerjoin(parent, parent.node_id == DocumentNode.parent_node_id)
        .where(
            DocumentNode.deleted_at.is_not(None),
            or_(
                DocumentNode.parent_node_id.is_(None),
                parent.node_id.is_(None),
                parent.deleted_at.is_(None),
            )
        )
        .order_by(DocumentNode.deleted_at.desc())
    )
    result = await db.execute(stmt)
    return result.all()

# Method to get every node_id and distinct document_id in a subtree, regardless of
# deletion state - used by permanent delete, which sweeps the whole subtree unconditionally.
async def get_subtree_ids(db: AsyncSession, path: str):
    stmt = select(DocumentNode.node_id, DocumentNode.document_id).where(DocumentNode.path.startswith(path))
    result = await db.execute(stmt)
    rows = result.all()
    node_ids = [row[0] for row in rows]
    document_ids = list({row[1] for row in rows})
    return node_ids, document_ids

# Method to permanently remove a node subtree. DocumentNode rows are removed first (they
# have no ON DELETE CASCADE from documents), then Document rows - whose removal cascades
# to content blocks and assets at the database level. Returns the removed document_ids so
# the caller can clean up their physical storage objects.
async def hard_delete_subtree(db: AsyncSession, path: str) -> list:
    node_ids, document_ids = await get_subtree_ids(db, path)
    if not node_ids:
        return []

    await db.execute(delete(DocumentNode).where(DocumentNode.node_id.in_(node_ids)))
    await db.execute(delete(Document).where(Document.id.in_(document_ids)))
    await db.commit()
    return document_ids
