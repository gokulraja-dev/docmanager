from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from app.db.debs import get_db
from .schemas import CreateContentBlockRequest, UpdateContentBlockRequest, ReorderContentBlocksRequest
from .usecases import (
    create_content_block_usecase,
    get_content_blocks_usecase,
    get_content_block_usecase,
    update_content_block_usecase,
    delete_content_block_usecase,
    reorder_content_blocks_usecase,
)

# Router initialization - content blocks are addressed by document_id, not node_id,
# since they belong to the Document content layer rather than the tree/hierarchy layer.
router = APIRouter(
    prefix="/documents/{document_id}/blocks",
    tags=["Document Content Blocks"]
)

# Dependencies
db = Annotated[AsyncSession, Depends(get_db)]

# Endpoint to create a new content block
@router.post("")
async def create_content_block_endpoint(db: db, document_id: str, request: CreateContentBlockRequest):
    return await create_content_block_usecase(db, document_id, request)

# Endpoint to list all content blocks of a document
@router.get("")
async def get_content_blocks_endpoint(db: db, document_id: str):
    return await get_content_blocks_usecase(db, document_id)

# Endpoint to reorder all content blocks of a document (registered before /{block_id} on purpose)
@router.put("/reorder")
async def reorder_content_blocks_endpoint(db: db, document_id: str, request: ReorderContentBlocksRequest):
    return await reorder_content_blocks_usecase(db, document_id, request)

# Endpoint to get a single content block
@router.get("/{block_id}")
async def get_content_block_endpoint(db: db, document_id: str, block_id: str):
    return await get_content_block_usecase(db, document_id, block_id)

# Endpoint to update a content block
@router.put("/{block_id}")
async def update_content_block_endpoint(db: db, document_id: str, block_id: str, request: UpdateContentBlockRequest):
    return await update_content_block_usecase(db, document_id, block_id, request)

# Endpoint to delete a content block
@router.delete("/{block_id}")
async def delete_content_block_endpoint(db: db, document_id: str, block_id: str):
    return await delete_content_block_usecase(db, document_id, block_id)
