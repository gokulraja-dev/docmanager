import hashlib
import json
import uuid
from fastapi import HTTPException, status, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.storage import get_storage_backend
from app.modules.documents.repository import get_document_by_id
from app.modules.documents.content_blocks.repository import get_blocks_by_document
from .repository import create_asset, get_asset, get_assets_by_document, delete_asset_record


# storage_key is an internal storage-implementation detail and is intentionally
# not exposed here - clients retrieve content via content_url instead.
def _serialize(asset) -> dict:
    return {
        "id": str(asset.id),
        "document_id": str(asset.document_id),
        "file_name": asset.file_name,
        "mime_type": asset.mime_type,
        "file_size": asset.file_size,
        "checksum": asset.checksum,
        "metadata": asset.meta,
        "content_url": f"/api/documents/{asset.document_id}/assets/{asset.id}/content",
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }

# Strips characters that could break the Content-Disposition header value
def _safe_content_disposition(file_name: str) -> str:
    safe_name = file_name.replace("\r", "").replace("\n", "").replace('"', "'")
    return f'inline; filename="{safe_name}"'

# Checks whether a content block's data references this asset (see content_blocks convention)
def _asset_referenced_in_block_data(data, asset_id: str) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("asset_id") == asset_id:
        return True
    asset_ids = data.get("asset_ids")
    if isinstance(asset_ids, list) and asset_id in asset_ids:
        return True
    return False

# Method to upload a new asset for a document
async def upload_asset_usecase(db: AsyncSession, document_id: str, file: UploadFile, metadata_raw: str | None):
    document = await get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    try:
        meta = json.loads(metadata_raw) if metadata_raw else {}
        if not isinstance(meta, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "metadata must be a valid JSON object")

    file_bytes = await file.read()
    checksum = hashlib.sha256(file_bytes).hexdigest()
    storage_key = f"documents/{document_id}/{uuid.uuid4()}_{file.filename}"

    storage = get_storage_backend()
    await storage.save(storage_key, file_bytes, content_type=file.content_type)

    # Storage write happens first: on DB failure we can clean up the orphaned
    # blob, whereas an orphaned DB row pointing at a missing blob is worse.
    try:
        asset = await create_asset(
            db,
            document_id,
            file.filename,
            file.content_type or "application/octet-stream",
            len(file_bytes),
            storage_key,
            checksum,
            meta,
        )
    except Exception:
        await storage.delete(storage_key)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to store asset metadata")

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(_serialize(asset)))

# Method to list all assets of a document
async def list_document_assets_usecase(db: AsyncSession, document_id: str):
    document = await get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assets = await get_assets_by_document(db, document_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"assets": jsonable_encoder([_serialize(a) for a in assets])})

# Method to get a single asset
async def get_asset_usecase(db: AsyncSession, document_id: str, asset_id: str):
    asset = await get_asset(db, document_id, asset_id)
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(_serialize(asset)))

# Method to delete an asset, refusing if a content block still references it
async def delete_asset_usecase(db: AsyncSession, document_id: str, asset_id: str):
    asset = await get_asset(db, document_id, asset_id)
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")

    blocks = await get_blocks_by_document(db, document_id)
    referencing = [str(b.id) for b in blocks if _asset_referenced_in_block_data(b.data, str(asset.id))]
    if referencing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Asset is referenced by {len(referencing)} content block(s) and cannot be deleted",
        )

    await delete_asset_record(db, document_id, asset_id)

    # DB is the source of truth; storage cleanup is best-effort afterwards.
    storage = get_storage_backend()
    try:
        await storage.delete(asset.storage_key)
    except Exception:
        pass

    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Asset deleted successfully"})

# Method to stream an asset's actual file content back to the client
async def download_asset_usecase(db: AsyncSession, document_id: str, asset_id: str):
    # Scoping the lookup by both asset_id and document_id means an asset_id
    # that belongs to a different document resolves to "not found" here, not a leak.
    asset = await get_asset(db, document_id, asset_id)
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")

    storage = get_storage_backend()
    try:
        stream = await storage.read_stream(asset.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset file is missing from storage")

    headers = {
        "Content-Disposition": _safe_content_disposition(asset.file_name),
        "Content-Length": str(asset.file_size),
    }
    return StreamingResponse(stream, media_type=asset.mime_type, headers=headers)
