from typing import Literal
from pydantic import BaseModel


class MemoryRecall(BaseModel):
    memory_names: list[str]

class MemoryChange(BaseModel):
    action_type: Literal["create", "adjust", "append", "delete"]
    memory_name: str
    memory_content: str
	
class MemoryChangeList(BaseModel):
    memory_changes: list[MemoryChange]
