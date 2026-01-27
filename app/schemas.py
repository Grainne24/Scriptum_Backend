'''
    This file defines what the data should look like when it comes in and goes out of the API which validates data automatically
'''
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID

#Login request
class UserLogin(BaseModel):
    email: str  # Can be email or username
    password: str

#Registration request
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)

#User response
class UserResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    username: str
    created_at: datetime
    is_active: bool
    last_login: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

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
    isbn: Optional[str] = None
    text_source: Optional[str] = None
    publication_year: Optional[int] = None
    text_file_path: Optional[str] = None
    analysed: Optional[bool] = None
    cover_url: Optional[str] = None

class BookResponse(BookBase):
    book_id: UUID
    created_at: datetime
    analyzed: bool
    summary: Optional[str] = None
    text_source: Optional[str] = None
    cover_url: Optional[str] = None
    pacing_score: Optional[float] = None
    tone_score: Optional[float] = None
    vocabulary_richness: Optional[float] = None
    avg_sentence_length: Optional[float] = None
    avg_word_length: Optional[float] = None
    lexical_diversity: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)

#Rating Schemas
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

#Error response
class ErrorResponse(BaseModel):
    detail: str
