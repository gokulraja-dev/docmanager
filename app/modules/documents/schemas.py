from pydantic import BaseModel
from typing import Any, Optional
from enum import Enum

# Schema model for create document request
class CreateDocumentRequest(BaseModel):
    title: str
    content: Any
    parent_node_id: Optional[str] = None

# Enumuration for document depth levels
class DocumentDepthLevel(str, Enum):
    ZERO = "0"
    ONE = "1"
    ALL = "all"

# Schema model for update document request
class UpdateDocumentRequest(BaseModel):
    title: str | None = None
    content: Any | None = None