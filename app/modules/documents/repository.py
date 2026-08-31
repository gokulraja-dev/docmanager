from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.orm import aliased
import uuid
from .model import Document, DocumentNode

# Method to create a new document, owned by the given account (org_id stays NULL for now)
async def create_document(db: AsyncSession, title: str, account_id, description: str | None = None, org_id=None):
    document = Document(title=title, description=description, account_id=account_id, org_id=org_id)
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document

# Method to get a document by id, scoped to the owning account
async def get_document_by_id(db: AsyncSession, document_id: str, account_id):
    stmt = select(Document).where(
        Document.id == document_id,
        Document.account_id == account_id,
        Document.deleted_at.is_(None),
    )
    return await db.scalar(stmt)

# Method to get a node by id (any deletion state), scoped to the owning account via its document
async def get_node_by_id(db: AsyncSession, node_id: str, account_id):
    stmt = (
        select(DocumentNode)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.node_id == node_id,
            Document.account_id == account_id,
        )
    )
    return await db.scalar(stmt)

# Method to create new node record
async def create_node_record(db: AsyncSession, node_id: str, document_id: str, parent_node_id: str, path: str):
    node = DocumentNode(node_id=node_id, document_id=document_id, parent_node_id=parent_node_id, path=path)
    db.add(node)
    await db.commit()
    await db.flush()
    await db.refresh(node)
    return node

# Method to get node with document, scoped to the owning account
async def get_node_with_document(db, node_id: str, account_id):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.node_id == node_id,
            Document.account_id == account_id,
            DocumentNode.deleted_at.is_(None)
        )
    )
    result = await db.execute(stmt)
    return result.first()


# Method to get immediate children, scoped to the owning account
async def get_immediate_children(db, parent_node_id: str, account_id):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.parent_node_id == parent_node_id,
            Document.account_id == account_id,
            DocumentNode.deleted_at.is_(None)
        )
        .order_by(DocumentNode.path)
    )
    result = await db.execute(stmt)
    return result.all()

# Method to get subtree, scoped to the owning account
async def get_subtree_nodes(db, path: str, account_id):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.path.startswith(path),
            Document.account_id == account_id,
            DocumentNode.deleted_at.is_(None)
        )
        .order_by(DocumentNode.path)
    )
    result = await db.execute(stmt)
    return result.all()

# Method to get root nodes (no parent) - used to list top-level documents, scoped to the account
async def get_root_nodes(db, account_id):
    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.parent_node_id.is_(None),
            Document.account_id == account_id,
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

# Method to soft delete a node subtree as one deletion batch, scoped to the owning account.
# Only nodes that are not already deleted are touched, so an independently-deleted
# descendant keeps its own deleted_at/deletion_batch_id from whenever it was originally deleted.
async def soft_delete_subtree(db: AsyncSession, path: str, account_id) -> uuid.UUID:
    batch_id = uuid.uuid4()
    now = func.now()
    owned_document_ids = select(Document.id).where(Document.account_id == account_id)

    result = await db.execute(
        update(DocumentNode)
        .where(
            DocumentNode.path.startswith(path),
            DocumentNode.deleted_at.is_(None),
            DocumentNode.document_id.in_(owned_document_ids),
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
# predates batch tracking, just that single node), scoped to the owning account.
async def restore_deletion_batch(db: AsyncSession, node: DocumentNode, account_id) -> list:
    if node.deletion_batch_id is not None:
        node_filter = DocumentNode.deletion_batch_id == node.deletion_batch_id
    else:
        node_filter = DocumentNode.node_id == node.node_id

    owned_document_ids = select(Document.id).where(Document.account_id == account_id)

    result = await db.execute(
        update(DocumentNode)
        .where(node_filter, DocumentNode.document_id.in_(owned_document_ids))
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

# Method to list the "roots" of deleted subtrees for one account: a deleted node whose
# parent is either absent or not itself deleted. Avoids showing every descendant of an
# already-listed subtree.
async def get_trash_root_nodes(db: AsyncSession, account_id):
    parent = aliased(DocumentNode)

    stmt = (
        select(DocumentNode, Document)
        .join(Document, Document.id == DocumentNode.document_id)
        .outerjoin(parent, parent.node_id == DocumentNode.parent_node_id)
        .where(
            Document.account_id == account_id,
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
# deletion state, scoped to the owning account - used by permanent delete, which sweeps
# the whole subtree unconditionally.
async def get_subtree_ids(db: AsyncSession, path: str, account_id):
    stmt = (
        select(DocumentNode.node_id, DocumentNode.document_id)
        .join(Document, Document.id == DocumentNode.document_id)
        .where(
            DocumentNode.path.startswith(path),
            Document.account_id == account_id,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()
    node_ids = [row[0] for row in rows]
    document_ids = list({row[1] for row in rows})
    return node_ids, document_ids

# Method to permanently remove a node subtree. DocumentNode rows are removed first (they
# have no ON DELETE CASCADE from documents), then Document rows - whose removal cascades
# to content blocks and assets at the database level. Returns the removed document_ids so
# the caller can clean up their physical storage objects. node_ids/document_ids must already
# be scoped to the owning account by the caller (see get_subtree_ids).
async def hard_delete_subtree(db: AsyncSession, node_ids: list, document_ids: list) -> list:
    if not node_ids:
        return []

    await db.execute(delete(DocumentNode).where(DocumentNode.node_id.in_(node_ids)))
    await db.execute(delete(Document).where(Document.id.in_(document_ids)))
    await db.commit()
    return document_ids
