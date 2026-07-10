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

class ProjectNoteCreate(BaseModel):
    body: str
    visibility: str = "private"

class ProjectTagAssign(BaseModel):
    tag_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    color: Optional[str] = None

class ProjectHintCreate(BaseModel):
    target_user_id: uuid.UUID
    body: str

class ProjectHintStatusUpdate(BaseModel):
    status: str

class ProjectThreadMessageCreate(BaseModel):
    body: str

class ProjectRenameRequest(BaseModel):
    new_name: str = Field(min_length=3, max_length=40)
    display_name: Optional[str] = Field(default=None, max_length=80)

class ProjectDisplayNameUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

class ProjectNotificationRead(BaseModel):
    read: bool = True
