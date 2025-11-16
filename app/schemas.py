'''
    This file defines what the data should look like when it comes in and goes out of the API which validates data automatically
'''
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID

# Login request
class UserLogin(BaseModel):
    email: str  # Can be email or username
    password: str

# Registration request
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)

# User response
class UserResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    username: str
    created_at: datetime
    is_active: bool
    last_login: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

# Error response
class ErrorResponse(BaseModel):
    detail: str
