from pydantic import BaseModel, model_validator

from .filter import QueryFilter

from typing import Optional, Self, List


class LlamaStackConfig(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None

    @model_validator(mode="after")
    def check_llama_stack_model(self) -> Self:
        if self.base_url is None:
            raise ValueError(
                "LLama stack URL is not specified"
            )
        return self

class ClientConfig(BaseModel):
    """Global service configuration."""
    name: str
    llama_stack: LlamaStackConfig
    query_validation_method: Optional[str]
    query_filters: List[QueryFilter] = []
