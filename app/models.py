'''
    This file defines what the database looks like in PostgreSQL and converts it to Python also known as ORM(Object Relational Mapping)
'''

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Float, CheckConstraint, TIMESTAMP, Date, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from app.database import Base

#User table
class User(Base):
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    last_login = Column(TIMESTAMP, nullable=True)
    is_active = Column(Boolean, default=True)
    
    #These are the relationships which connect tables together
    recommendations = relationship("Recommendation", back_populates="user", cascade="all, delete-orphan")

#Book table
class Book(Base):
    __tablename__ = "books"
    
    book_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gutenberg_id = Column(Integer, unique=True, nullable=True, index=True)
    title = Column(String(500), nullable=False)
    author = Column(String(255), nullable=False, index=True)
    publication_year = Column(Integer, nullable=True)
    summary = Column(Text)
    text_file_path = Column(Text, nullable=True)
    cover_url = Column(String(500), nullable=True)
    text_source = Column(String(100), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    analysed = Column(Boolean, default=False, index=True)
    genres = Column(Text, nullable=True)
    
    # Relationships
    stylometric_profile = relationship("StylometricProfile", back_populates="book", uselist=False, cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="book", cascade="all, delete-orphan")

#User Book table
class UserBookshelf(Base):
    __tablename__ = "user_bookshelf"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(TIMESTAMP, server_default=func.now())
    book_status = Column(String(50), default='want_to_read')
    comments = Column(Text, nullable=True)
    date_started = Column(Date, nullable=True)
    date_ended = Column(Date, nullable=True)
    rating = Column(Numeric(3, 2), nullable=True)
    rated_at = Column(TIMESTAMP, nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True)

#Stylometric profile table
class StylometricProfile(Base):
    __tablename__ = "stylometric_profiles"
    
    profile_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="CASCADE"), unique=True, nullable=False)
    pacing_score = Column(Numeric(5, 2), nullable=True)
    tone_score = Column(Numeric(5, 2), nullable=True)
    vocabulary_richness = Column(Numeric(5, 2), nullable=True)
    avg_sentence_length = Column(Numeric(6, 2), nullable=True)
    avg_word_length = Column(Numeric(5, 2), nullable=True)
    lexical_diversity = Column(Numeric(5, 4), nullable=True)
    punctuation_density = Column(Numeric(5, 4), nullable=True)  
    dialogue_percentage = Column(Numeric(5, 2), nullable=True)  
    total_words = Column(Integer, nullable=True)
    total_sentences = Column(Integer, nullable=True)
    unique_words = Column(Integer, nullable=True)
    analysis_version = Column(String(20), nullable=True)
    analysed_at = Column(TIMESTAMP, server_default=func.now())
    
    #Relationships
    book = relationship("Book", back_populates="stylometric_profile")

#Recommendation table
class Recommendation(Base):
    __tablename__ = "recommendations"

    recommendation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id"), nullable=False)
    rank = Column(Integer, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    viewed = Column(Boolean, default=False)
    viewed_at = Column(DateTime, nullable=True)
    
    #Relationships
    user = relationship("User", back_populates="recommendations")
    book = relationship("Book", back_populates="recommendations")