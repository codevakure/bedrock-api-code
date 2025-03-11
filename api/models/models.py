from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FilterMode(Enum):
    REMOVE = "remove"
    MASK = "mask"
    BLOCK = "block"


class GuardrailSettings(BaseModel):
    guardrailIdentifier: str = "e1xjb1vcaxah"
    guardrailVersion: str = "DRAFT"


class GenerationSettings(BaseModel):
    temperature: float = Field(
        default=0.2, ge=0, le=1, description="Controls randomness in the output"
    )
    top_p: float = Field(default=0.999, ge=0, le=1, description="Nucleus sampling parameter")
    top_k: int = Field(default=250, ge=0, description="Top-k sampling parameter")
    max_tokens: int = Field(default=2048, ge=0, description="Maximum number of tokens to generate")
    stop_sequences: Optional[List[str]] = Field(
        default=None, description="Sequences that will stop generation"
    )
    guardrails: Optional[GuardrailSettings] = None


class QueryRequest(BaseModel):
    prompt: str
    document_id: Optional[str] = None
    settings: Optional[GenerationSettings] = None
    system_prompt: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    model_arn: Optional[str] = None


class ModelInfo(BaseModel):
    model_arn: str
    description: str


class ModelResponse(BaseModel):
    models: List[ModelInfo]


class UploadResponse(BaseModel):
    message: str
    filename: str
    original_filename: str


class DocumentDetails(BaseModel):
    key: str
    size: int
    last_modified: str
    content_type: str
    metadata: Dict[str, Any]


class SyncStatus(BaseModel):
    is_syncing: bool
    status: str
    last_sync_start: Optional[str]
    last_sync_complete: Optional[str]
    error_message: Optional[str]
