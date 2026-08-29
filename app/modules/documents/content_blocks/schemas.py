from pydantic import BaseModel, Field
from typing import Any, Optional

# Schema for create content block request
class CreateContentBlockRequest(BaseModel):
    block_type: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    position: Optional[int] = None

# Schema for update content block request
class UpdateContentBlockRequest(BaseModel):
    block_type: Optional[str] = None
    data: Optional[dict[str, Any]] = None

# Schema for reordering all content blocks of a document in one call
class ReorderContentBlocksRequest(BaseModel):
    block_ids: list[str]
