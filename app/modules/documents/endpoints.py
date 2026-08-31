from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from app.db.debs import get_db
from app.security import check_permission
from .usecases import (
    create_document_usecase,
    get_document_usecase,
    delete_document_usecase,
    update_document_usecase,
    list_documents_usecase,
    list_trash_usecase,
    restore_document_usecase,
    permanently_delete_document_usecase,
)
from .schemas import CreateDocumentRequest, DocumentDepthLevel, UpdateDocumentRequest

# Router initialization
router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

# Dependencies
db = Annotated[AsyncSession, Depends(get_db)]

# Endpoint to create a new document. Ownership comes only from the IAM token's `sub`
# claim - the client cannot supply account_id/org_id.
@router.post("")
async def create_document_endpoint(db: db, request: CreateDocumentRequest, current_user: dict = Depends(check_permission("create-document"))):
    resp = await create_document_usecase(db, current_user.get("sub"), request)
    return resp

# Endpoint to list root (top-level) documents
@router.get("")
async def list_documents_endpoint(depth: DocumentDepthLevel = Query(DocumentDepthLevel.ZERO), db: AsyncSession = Depends(get_db), current_user: dict = Depends(check_permission("read-document"))):
    return await list_documents_usecase(db, current_user.get("sub"), depth.value)

# Endpoint to list the trash - registered before /{node_id} so "trash" is never
# captured as a node_id path parameter.
@router.get("/trash")
async def get_trash_endpoint(db: db, current_user: dict = Depends(check_permission("read-document"))):
    return await list_trash_usecase(db, current_user.get("sub"))

# Endpoint to get a document
@router.get("/{node_id}")
async def get_document_endpoint(node_id: str, depth: DocumentDepthLevel = Query(DocumentDepthLevel.ZERO), db: AsyncSession = Depends(get_db), current_user: dict = Depends(check_permission("read-document"))):
    return await get_document_usecase(db, current_user.get("sub"), node_id, depth.value)

# Endpoint to update a document
@router.put("/{node_id}")
async def update_document_endpoint(node_id: str, request: UpdateDocumentRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(check_permission("update-document"))):
    return await update_document_usecase(db, current_user.get("sub"), node_id, request)

# Endpoint to soft delete a document (moves it to trash)
@router.delete("/{node_id}")
async def delete_document_endpoint(node_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(check_permission("delete-document"))):
    return await delete_document_usecase(db, current_user.get("sub"), node_id)

# Endpoint to restore a deleted document
@router.post("/{node_id}/restore")
async def restore_document_endpoint(db: db, node_id: str, current_user: dict = Depends(check_permission("restore-document"))):
    return await restore_document_usecase(db, current_user.get("sub"), node_id)

# Endpoint to irreversibly delete a document already in the trash
@router.delete("/{node_id}/permanent")
async def permanently_delete_document_endpoint(db: db, node_id: str, current_user: dict = Depends(check_permission("permanent-delete-document"))):
    return await permanently_delete_document_usecase(db, current_user.get("sub"), node_id)
