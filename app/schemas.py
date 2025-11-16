'''
    This file defines what the data should look like when it comes in and goes out of the API which validates data automatically
'''
#pydantic - data validation + settings management
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)

#Schema for creating a user e.g. must be of valid email format
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    email: str  # Can be email or username
    password: str

#Schema for returning data so what the API sends back
class UserResponse(BaseModel):
    user_id: UUID
    created_at: datetime
    is_active: bool
    last_login: Optional[datetime] = None
    
    #This tells the pydantic to work with SQLAlchemy models
    model_config = ConfigDict(from_attributes=True)

# Book Schemas
class BookBase(BaseModel):
    title: str = Field(..., max_length=500)
    author: str = Field(..., max_length=255)
    publication_year: Optional[int] = None
    isbn: Optional[str] = Field(None, max_length=13)

class BookCreate(BookBase):
    text_file_path: Optional[str] = None
    text_source: Optional[str] = None

class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    publication_year: Optional[int] = None
    text_file_path: Optional[str] = None
    analyzed: Optional[bool] = None

class BookResponse(BookBase):
    book_id: UUID
    created_at: datetime
    analyzed: bool
    text_source: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# Rating Schemas
class RatingCreate(BaseModel):
    book_id: UUID
    rating: float = Field(..., ge=0.0, le=10.0)
    review_text: Optional[str] = None

class RatingResponse(BaseModel):
    rating_id: UUID
    user_id: UUID
    book_id: UUID
    rating: float
    review_text: Optional[str]
    rated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
