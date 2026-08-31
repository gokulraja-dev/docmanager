from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.storage import get_storage_backend
from .repository import (
    get_node_by_id,
    create_document,
    create_node_record,
    get_node_with_document,
    get_subtree_nodes,
    get_immediate_children,
    soft_delete_subtree,
    restore_deletion_batch,
    get_trash_root_nodes,
    get_subtree_ids,
    hard_delete_subtree,
    update_document,
    get_root_nodes,
)
from .utilis import generate_ulid, build_tree_response, build_node_response
from .schemas import CreateDocumentRequest, UpdateDocumentRequest
from .content_blocks.repository import get_blocks_by_document_ids
from .assets.repository import get_assets_by_document_ids

# Method to create a new document, owned by the authenticated account. org_id stays NULL
# for now - organization scoping is a later phase.
async def create_document_usecase(db: AsyncSession, account_id, payload: CreateDocumentRequest):
    # Constants
    PATH = None
    node_id = generate_ulid()

    # Step 1: Validate the parent (if any) before creating anything, so a rejected
    # parent never leaves an orphaned Document with no DocumentNode behind it.
    if payload.parent_node_id is not None:
        # Scoped to the account: a parent belonging to another account resolves to
        # "not found" here, never leaking that it exists.
        parent = await get_node_by_id(db, payload.parent_node_id, account_id)

        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent Document not found")

        if parent.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot create a document under a deleted parent")

        PATH = f"{parent.path}.{node_id}"
    else:
        PATH = node_id

    # Step 2: Create a new document owned by the caller's account
    document = await create_document(db, payload.title, account_id, description=payload.description)

    # Step 3: Create a new node record
    node = await create_node_record(db, node_id, document.id, payload.parent_node_id, PATH)

    # Preparing the return response
    result = {
        "document_id": document.id,
        "node_id": node.node_id,
        "path": node.path
    }

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(result))


# Method to list root (top-level) documents belonging to the account, same depth semantics as get_document_usecase
async def list_documents_usecase(db: AsyncSession, account_id, depth: str):
    roots = await get_root_nodes(db, account_id)
    if not roots:
        return {"documents": []}

    if depth == "0":
        document_ids = [document.id for _, document in roots]
        blocks_map = await get_blocks_by_document_ids(db, document_ids)
        documents = [
            build_node_response(node, document, blocks_map.get(document.id, []))
            for node, document in roots
        ]
        return {"documents": documents}

    if depth == "1":
        documents = []
        for node, document in roots:
            children_rows = await get_immediate_children(db, node.node_id, account_id)
            document_ids = [document.id] + [child_document.id for _, child_document in children_rows]
            blocks_map = await get_blocks_by_document_ids(db, document_ids)

            children = [
                build_node_response(child_node, child_document, blocks_map.get(child_document.id, []))
                for child_node, child_document in children_rows
            ]
            documents.append(build_node_response(node, document, blocks_map.get(document.id, []), children=children))
        return {"documents": documents}

    if depth == "all":
        documents = []
        for node, _ in roots:
            rows = await get_subtree_nodes(db, node.path, account_id)
            document_ids = [row_document.id for _, row_document in rows]
            blocks_map = await get_blocks_by_document_ids(db, document_ids)
            documents.append(build_tree_response(rows, blocks_map))
        return {"documents": documents}

    raise HTTPException(400, "Invalid depth parameter")


# Method to get a document, scoped to the authenticated account
async def get_document_usecase(db, account_id, node_id: str, depth: str):

    # Step 1: Fetch base node - only resolves if it belongs to this account
    row = await get_node_with_document(db, node_id, account_id)
    if not row:
        raise HTTPException(404, "Document not found")

    node, document = row

    # depth = 0 → only this node
    if depth == "0":
        blocks_map = await get_blocks_by_document_ids(db, [document.id])
        return build_node_response(node, document, blocks_map.get(document.id, []))

    # depth = 1 → only immediate children (also account-scoped, so a cross-account
    # child could never be attached here in the first place, but scoped anyway)
    if depth == "1":
        children_rows = await get_immediate_children(db, node.node_id, account_id)
        document_ids = [document.id] + [child_document.id for _, child_document in children_rows]
        blocks_map = await get_blocks_by_document_ids(db, document_ids)

        children = [
            build_node_response(child_node, child_document, blocks_map.get(child_document.id, []))
            for child_node, child_document in children_rows
        ]
        return build_node_response(node, document, blocks_map.get(document.id, []), children=children)

    # depth = all → full subtree, account-scoped so traversal can never cross into another account
    if depth == "all":
        rows = await get_subtree_nodes(db, node.path, account_id)
        document_ids = [row_document.id for _, row_document in rows]
        blocks_map = await get_blocks_by_document_ids(db, document_ids)
        return build_tree_response(rows, blocks_map)

    raise HTTPException(400, "Invalid depth parameter")


# Mehtod to update a document, scoped to the authenticated account
async def update_document_usecase(db: AsyncSession, account_id, node_id: str, payload: UpdateDocumentRequest):
    # Step 1: Check if the document exists and belongs to this account
    row = await get_node_with_document(db, node_id, account_id)

    if not row:
        raise HTTPException(404, "Document not found")

    node, document = row

    # Step 2: Update the document
    await update_document(db, document, title=payload.title, description=payload.description)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Document updated successfully", "node_id": node.node_id})

# Method to soft delete a document (and its active descendants) as one recoverable operation,
# scoped to the authenticated account
async def delete_document_usecase(db: AsyncSession, account_id, node_id: str):
    # Step 1: Check if the node exists at all (any state) and belongs to this account
    node = await get_node_by_id(db, node_id, account_id)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    # Step 2: Reject if it's already in the trash
    if node.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already deleted")

    # Step 3: Soft delete the node subtree as one batch
    await soft_delete_subtree(db, node.path, account_id)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Document deleted successfully", "node_id": node.node_id})

# Method to list the trash for the authenticated account: one entry per independently-deleted subtree root
async def list_trash_usecase(db: AsyncSession, account_id):
    rows = await get_trash_root_nodes(db, account_id)
    entries = [
        {
            "node_id": node.node_id,
            "document_id": str(document.id),
            "title": document.title,
            "description": document.description,
            "deleted_at": node.deleted_at,
        }
        for node, document in rows
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content={"trash": jsonable_encoder(entries)})

# Method to restore a deleted document, along with whatever was deleted in the same
# operation, scoped to the authenticated account
async def restore_document_usecase(db: AsyncSession, account_id, node_id: str):
    # Step 1: Check if the node exists at all (any state) and belongs to this account
    node = await get_node_by_id(db, node_id, account_id)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    # Step 2: Reject if it's already active
    if node.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already active")

    # Step 3: Restore this node's deletion batch (independently deleted descendants are untouched)
    await restore_deletion_batch(db, node, account_id)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Document restored successfully", "node_id": node.node_id})

# Method to irreversibly remove a document subtree: DB records and physical asset files.
# Only allowed on a document that has already been soft-deleted (is in the trash), and
# scoped to the authenticated account throughout.
async def permanently_delete_document_usecase(db: AsyncSession, account_id, node_id: str):
    # Step 1: Check if the node exists at all (any state) and belongs to this account
    node = await get_node_by_id(db, node_id, account_id)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    # Step 2: Require it to already be in the trash - permanent delete never applies to active documents
    if node.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document must be deleted (in trash) before it can be permanently deleted")

    # Step 3: Determine the full subtree (account-scoped) and gather asset storage_keys
    # before anything is removed. The sweep covers the whole subtree unconditionally (not
    # just already-deleted descendants), since permanent deletion of a node necessarily
    # removes everything beneath it.
    node_ids, document_ids = await get_subtree_ids(db, node.path, account_id)
    assets = await get_assets_by_document_ids(db, document_ids)
    storage_keys = [asset.storage_key for asset in assets]

    # Step 4: Remove database records. DocumentNode rows are deleted first, then Document rows
    # (which cascades to content blocks and assets at the database level).
    removed_document_ids = await hard_delete_subtree(db, node_ids, document_ids)

    # Step 5: Best-effort cleanup of physical storage objects. The database change is already
    # committed and cannot be rolled back together with storage, so failures are reported,
    # not swallowed or retried silently.
    storage = get_storage_backend()
    failed_keys = []
    for key in storage_keys:
        try:
            await storage.delete(key)
        except Exception:
            failed_keys.append(key)

    result = {
        "msg": "Document permanently deleted",
        "node_id": node.node_id,
        "documents_removed": len(removed_document_ids),
        "assets_removed": len(storage_keys) - len(failed_keys),
    }
    if failed_keys:
        result["storage_cleanup_warning"] = (
            f"{len(failed_keys)} asset file(s) could not be removed from storage and may be orphaned"
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(result))
