from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None  # For password change verification
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role: Optional[str] = None


class UserInDB(UserBase):
    id: int
    role: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True


class User(UserInDB):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
