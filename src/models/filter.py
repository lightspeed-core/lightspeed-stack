import re
from pydantic import BaseModel

class QueryFilter(BaseModel):
    name: str
    pattern: str
    replace_with: str

    def filter(self, q):
        return re.sub(self.pattern, self.replace_with, q, flags=re.IGNORECASE)