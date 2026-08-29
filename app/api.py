from fastapi import APIRouter
from app.modules.documents.endpoints import router as documents_router
from app.modules.documents.content_blocks.endpoints import router as content_blocks_router
from app.modules.documents.assets.endpoints import router as assets_router

api_router = APIRouter()
api_router.include_router(documents_router)
api_router.include_router(content_blocks_router)
api_router.include_router(assets_router)
