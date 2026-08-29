from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.modules.documents.model import DocumentAsset

# Method to create a new asset record
async def create_asset(db: AsyncSession, document_id: str, file_name: str, mime_type: str, file_size: int, storage_key: str, checksum: str, meta: dict):
    asset = DocumentAsset(
        document_id=document_id,
        file_name=file_name,
        mime_type=mime_type,
        file_size=file_size,
        storage_key=storage_key,
        checksum=checksum,
        meta=meta,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset

# Method to get a single asset scoped to its document
async def get_asset(db: AsyncSession, document_id: str, asset_id: str):
    stmt = select(DocumentAsset).where(
        DocumentAsset.id == asset_id,
        DocumentAsset.document_id == document_id,
    )
    return await db.scalar(stmt)

# Method to get all assets of a document
async def get_assets_by_document(db: AsyncSession, document_id: str):
    stmt = (
        select(DocumentAsset)
        .where(DocumentAsset.document_id == document_id)
        .order_by(DocumentAsset.created_at)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# Method to get a specific set of assets belonging to a document (used for reference validation)
async def get_assets_by_ids(db: AsyncSession, document_id: str, asset_ids: list[str]):
    if not asset_ids:
        return []

    stmt = select(DocumentAsset).where(
        DocumentAsset.document_id == document_id,
        DocumentAsset.id.in_(asset_ids),
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# Method to delete an asset record
async def delete_asset_record(db: AsyncSession, document_id: str, asset_id: str) -> bool:
    stmt = delete(DocumentAsset).where(
        DocumentAsset.id == asset_id,
        DocumentAsset.document_id == document_id,
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0
