from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from .repository import get_node_by_id, create_document, create_node_record, get_node_with_document, get_subtree_nodes, get_immediate_children, soft_delete_node_record, get_node, update_document
from .utilis import generate_ulid, build_tree_response
from .schemas import CreateDocumentRequest, UpdateDocumentRequest

# Method to create a new document
async def create_document_usecase(db: AsyncSession, payload: CreateDocumentRequest):
    # Constants
    PATH = None

    # Step 1: Create a new document
    document = await create_document(db, payload.title, payload.content)

    # Step 2: Document tree logic
    node_id = generate_ulid()

    if payload.parent_node_id is not None:
        parent = await get_node_by_id(db, payload.parent_node_id)

        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent Document not found")

        PATH = f"{parent.path}.{node_id}"
    else:
        PATH = node_id

    # Step 3: Create a new node record
    node = await create_node_record(db, node_id, document.id, payload.parent_node_id, PATH)

    # Preparing the return response
    result = {
        "document_id": document.id,
        "node_id": node.node_id,
        "path": node.path
    }

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(result))


# Method to get a document
async def get_document_usecase(db, node_id: str, depth: str):

    # Step 1: Fetch base node
    row = await get_node_with_document(db, node_id)
    if not row:
        raise HTTPException(404, "Document not found")

    node, document = row

    base_response = {
        "node_id": node.node_id,
        "title": document.title,
        "content": document.content,
        "parent_node_id": node.parent_node_id,
        "children": []
    }

    # depth = 0 → only this node
    if depth == "0":
        return base_response

    # depth = 1 → only immediate children
    if depth == "1":
        children = await get_immediate_children(db, node.node_id)

        base_response["children"] = [
            {
                "node_id": child.node_id,
                "title": doc.title,
                "content": doc.content,
                "parent_node_id": child.parent_node_id,
                "children": []
            }
            for child, doc in children
        ]
        return base_response

    # depth = all → full subtree
    if depth == "all":
        rows = await get_subtree_nodes(db, node.path)
        return build_tree_response(rows)

    raise HTTPException(400, "Invalid depth parameter")


# Mehtod to update a document
async def update_document_usecase(db: AsyncSession, node_id: str, payload: CreateDocumentRequest):
    # Step 1: Check if the document exists
    row = await get_node_with_document(db, node_id)

    if not row:
        raise HTTPException(404, "Document not found")

    node, document = row

    # Step 2: Update the document
    await update_document(db, document, payload.title, payload.content)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Document updated successfully", "node_id": node.node_id})

# Method to delete a document
async def delete_document_usecase(db: AsyncSession, node_id: str):
    # Step 1: Check if the document exists
    document = await get_node(db, node_id)
    if not document:
        raise HTTPException(404, "Document not found")

    # Step 2: Soft delete the document
    await soft_delete_node_record(db, document.path)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"msg": "Document deleted successfully"})