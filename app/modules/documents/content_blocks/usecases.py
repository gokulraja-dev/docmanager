from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.documents.repository import get_document_by_id
from app.modules.documents.assets.repository import get_assets_by_ids
from app.modules.documents.utilis import serialize_block
from .schemas import CreateContentBlockRequest, UpdateContentBlockRequest, ReorderContentBlocksRequest
from .repository import (
    create_block,
    get_block,
    get_blocks_by_document,
    get_max_position,
    update_block,
    delete_block,
    set_block_positions,
)

# A block's `data` may reference assets via an "asset_id" or "asset_ids" key.
# This is a convention, not a hard schema, so new block types can adopt it without migrations.
def _extract_asset_ids(data: dict) -> list[str]:
    ids = []
    if not isinstance(data, dict):
        return ids

    single = data.get("asset_id")
    if isinstance(single, str):
        ids.append(single)

    multiple = data.get("asset_ids")
    if isinstance(multiple, list):
        ids.extend([a for a in multiple if isinstance(a, str)])

    return ids

# Ensures any asset referenced from block data actually belongs to this document
async def _validate_asset_references(db: AsyncSession, document_id: str, data: dict):
    asset_ids = _extract_asset_ids(data)
    if not asset_ids:
        return

    found = await get_assets_by_ids(db, document_id, asset_ids)
    found_ids = {str(asset.id) for asset in found}
    missing = [asset_id for asset_id in asset_ids if asset_id not in found_ids]

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Referenced asset(s) not found on this document: {', '.join(missing)}",
        )

# Ownership flows through document_id -> Document.account_id (never a separate
# account_id on the block itself). A document belonging to another account - or that
# doesn't exist - resolves to "not found" here, never leaking existence.
async def _require_owned_document(db: AsyncSession, document_id: str, account_id):
    document = await get_document_by_id(db, document_id, account_id)
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document

# Method to create a new content block
async def create_content_block_usecase(db: AsyncSession, account_id, document_id: str, payload: CreateContentBlockRequest):
    await _require_owned_document(db, document_id, account_id)

    await _validate_asset_references(db, document_id, payload.data)

    position = payload.position
    if position is None:
        position = await get_max_position(db, document_id) + 1

    block = await create_block(db, document_id, payload.block_type, payload.data, position)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(serialize_block(block)))

# Method to list all content blocks of a document
async def get_content_blocks_usecase(db: AsyncSession, account_id, document_id: str):
    await _require_owned_document(db, document_id, account_id)

    blocks = await get_blocks_by_document(db, document_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"blocks": jsonable_encoder([serialize_block(b) for b in blocks])})

# Method to get a single content block
async def get_content_block_usecase(db: AsyncSession, account_id, document_id: str, block_id: str):
    await _require_owned_document(db, document_id, account_id)

    block = await get_block(db, document_id, block_id)
    if not block:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content block not found")

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(serialize_block(block)))

# Method to update a content block
async def update_content_block_usecase(db: AsyncSession, account_id, document_id: str, block_id: str, payload: UpdateContentBlockRequest):
    await _require_owned_document(db, document_id, account_id)

    block = await get_block(db, document_id, block_id)
    if not block:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content block not found")

    if payload.data is not None:
        await _validate_asset_references(db, document_id, payload.data)

    block = await update_block(db, block, block_type=payload.block_type, data=payload.data)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(serialize_block(block)))

# Method to delete a content block
async def delete_content_block_usecase(db: AsyncSession, account_id, document_id: str, block_id: str):
    await _require_owned_document(db, document_id, account_id)

    block = await get_block(db, document_id, block_id)
    if not block:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content block not found")

    await delete_block(db, document_id, block_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Content block deleted successfully"})

# Method to reorder all content blocks of a document in one call
async def reorder_content_blocks_usecase(db: AsyncSession, account_id, document_id: str, payload: ReorderContentBlocksRequest):
    await _require_owned_document(db, document_id, account_id)

    existing_blocks = await get_blocks_by_document(db, document_id)
    existing_ids = {str(b.id) for b in existing_blocks}

    if set(payload.block_ids) != existing_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "block_ids must include exactly the current set of content blocks for this document",
        )

    await set_block_positions(db, document_id, payload.block_ids)
    blocks = await get_blocks_by_document(db, document_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"blocks": jsonable_encoder([serialize_block(b) for b in blocks])})
