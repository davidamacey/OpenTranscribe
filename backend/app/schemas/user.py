from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field

from app.schemas.base import UUIDBaseSchema


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: Optional[str] = "user"
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None  # For password change verification
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role: Optional[str] = None


class UserInDB(UserBase, UUIDBaseSchema):
    """User schema with UUID as public identifier"""

    role: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    is_superuser: bool
    auth_type: str
    ldap_uid: Optional[str] = None


class User(UserInDB):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
