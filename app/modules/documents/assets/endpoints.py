from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Optional
from app.db.debs import get_db
from .usecases import upload_asset_usecase, list_document_assets_usecase, get_asset_usecase, delete_asset_usecase, download_asset_usecase

# Router initialization - assets are addressed by document_id, same as content blocks
router = APIRouter(
    prefix="/documents/{document_id}/assets",
    tags=["Document Assets"]
)

# Dependencies
db = Annotated[AsyncSession, Depends(get_db)]

# Endpoint to upload a new asset for a document
@router.post("")
async def upload_asset_endpoint(db: db, document_id: str, file: UploadFile = File(...), metadata: Optional[str] = Form(None)):
    return await upload_asset_usecase(db, document_id, file, metadata)

# Endpoint to list all assets of a document
@router.get("")
async def list_document_assets_endpoint(db: db, document_id: str):
    return await list_document_assets_usecase(db, document_id)

# Endpoint to get a single asset's metadata
@router.get("/{asset_id}")
async def get_asset_endpoint(db: db, document_id: str, asset_id: str):
    return await get_asset_usecase(db, document_id, asset_id)

# Endpoint to stream the asset's actual file content
@router.get("/{asset_id}/content")
async def get_asset_content_endpoint(db: db, document_id: str, asset_id: str):
    return await download_asset_usecase(db, document_id, asset_id)

# Endpoint to delete an asset
@router.delete("/{asset_id}")
async def delete_asset_endpoint(db: db, document_id: str, asset_id: str):
    return await delete_asset_usecase(db, document_id, asset_id)
