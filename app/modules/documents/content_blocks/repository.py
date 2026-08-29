from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from app.modules.documents.model import DocumentContentBlock

# Method to create a new content block
async def create_block(db: AsyncSession, document_id: str, block_type: str, data: dict, position: int):
    block = DocumentContentBlock(document_id=document_id, block_type=block_type, data=data, position=position)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block

# Method to get a single content block scoped to its document
async def get_block(db: AsyncSession, document_id: str, block_id: str):
    stmt = select(DocumentContentBlock).where(
        DocumentContentBlock.id == block_id,
        DocumentContentBlock.document_id == document_id,
    )
    return await db.scalar(stmt)

# Method to get all content blocks of a document, ordered by position
async def get_blocks_by_document(db: AsyncSession, document_id: str):
    stmt = (
        select(DocumentContentBlock)
        .where(DocumentContentBlock.document_id == document_id)
        .order_by(DocumentContentBlock.position)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# Method to get content blocks for several documents in one query, grouped by document id
async def get_blocks_by_document_ids(db: AsyncSession, document_ids: list):
    if not document_ids:
        return {}

    stmt = (
        select(DocumentContentBlock)
        .where(DocumentContentBlock.document_id.in_(document_ids))
        .order_by(DocumentContentBlock.document_id, DocumentContentBlock.position)
    )
    result = await db.execute(stmt)

    blocks_map = {}
    for block in result.scalars().all():
        blocks_map.setdefault(block.document_id, []).append(block)
    return blocks_map

# Method to get the current highest position used in a document's blocks
async def get_max_position(db: AsyncSession, document_id: str) -> int:
    stmt = select(func.max(DocumentContentBlock.position)).where(DocumentContentBlock.document_id == document_id)
    result = await db.scalar(stmt)
    return result if result is not None else -1

# Method to update a content block
async def update_block(db: AsyncSession, block: DocumentContentBlock, block_type: str | None = None, data: dict | None = None):
    if block_type is not None:
        block.block_type = block_type
    if data is not None:
        block.data = data
    await db.commit()
    await db.refresh(block)
    return block

# Method to delete a content block
async def delete_block(db: AsyncSession, document_id: str, block_id: str) -> bool:
    stmt = delete(DocumentContentBlock).where(
        DocumentContentBlock.id == block_id,
        DocumentContentBlock.document_id == document_id,
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

# Method to rewrite the position of every block in a document to match the given order
async def set_block_positions(db: AsyncSession, document_id: str, ordered_block_ids: list[str]):
    for index, block_id in enumerate(ordered_block_ids):
        await db.execute(
            update(DocumentContentBlock)
            .where(
                DocumentContentBlock.id == block_id,
                DocumentContentBlock.document_id == document_id,
            )
            .values(position=index)
        )
    await db.commit()
