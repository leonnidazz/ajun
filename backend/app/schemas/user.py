import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    campus_name: Optional[str] = None
    campus_domain_match: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
