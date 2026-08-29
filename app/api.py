from fastapi import APIRouter
from app.modules.documents.endpoints import router as documents_router

api_router = APIRouter()
api_router.include_router(documents_router)
