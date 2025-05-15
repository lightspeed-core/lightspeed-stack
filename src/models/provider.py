from pydantic import BaseModel

from typing import List


class Provider(BaseModel):
    name: str
    models: List[str]