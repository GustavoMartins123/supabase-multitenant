import uuid
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class NewProject(BaseModel):
    name: str

class DuplicateProject(BaseModel):
    original_name: str
    new_name: str
    copy_data: bool = False

class UserSyncPayload(BaseModel):
    id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    groups: List[str] = Field(default_factory=list)
    is_active: bool = True
    source: str = "studio_sync"

class AddMember(BaseModel):
    user_id: str
    role: str = 'member'

class TransferBody(BaseModel):
    new_owner_id: str

class UpdateSettings(BaseModel):
    settings: Dict[str, str]

class RecreateServices(BaseModel):
    services: List[str]
