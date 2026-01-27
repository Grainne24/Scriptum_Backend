'''
    This file defines what the database looks like in PostgreSQL and converts it to Python also known as ORM(Object Relational Mapping)
'''

from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, DECIMAL, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base

#User table
class User(Base):
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    last_login = Column(TIMESTAMP, nullable=True)
    is_active = Column(Boolean, default=True)
    
    #These are the relationships which connect tables together
    ratings = relationship("Rating", back_populates="user", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="user", cascade="all, delete-orphan")

#Book table
class Book(Base):
    __tablename__ = "books"
    
    book_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gutenberg_id = Column(Integer, unique=True, nullable=True, index=True)
    title = Column(String(500), nullable=False)
    author = Column(String(255), nullable=False, index=True)
    publication_year = Column(Integer, nullable=True)
    isbn = Column(String(13), nullable=True)
    summary = Column(Text)
    text_file_path = Column(Text, nullable=True)
    cover_url = Column(String(500), nullable=True)
    text_source = Column(String(100), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    analyzed = Column(Boolean, default=False, index=True)
    
    # Relationships
    stylometric_profile = relationship("StylometricProfile", back_populates="book", uselist=False, cascade="all, delete-orphan")
    ratings = relationship("Rating", back_populates="book", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="book", cascade="all, delete-orphan")

#Stylometric profile table
class StylometricProfile(Base):
    __tablename__ = "stylometric_profiles"
    
    profile_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="CASCADE"), unique=True, nullable=False)
    pacing_score = Column(DECIMAL(5, 2), nullable=True)
    tone_score = Column(DECIMAL(5, 2), nullable=True)
    vocabulary_richness = Column(DECIMAL(5, 2), nullable=True)
    avg_sentence_length = Column(DECIMAL(6, 2), nullable=True)
    avg_word_length = Column(DECIMAL(5, 2), nullable=True)
    lexical_diversity = Column(DECIMAL(5, 4), nullable=True)
    punctuation_density = Column(DECIMAL(5, 4), nullable=True)  
    dialogue_percentage = Column(DECIMAL(5, 2), nullable=True)  
    total_words = Column(Integer, nullable=True)
    total_sentences = Column(Integer, nullable=True)
    unique_words = Column(Integer, nullable=True)
    analysis_version = Column(String(20), nullable=True)
    analyzed_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    book = relationship("Book", back_populates="stylometric_profile")

#Rating table
class Rating(Base):
    __tablename__ = "ratings"
    
    rating_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(DECIMAL(3, 2), nullable=False)
    review_text = Column(Text, nullable=True)
    rated_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="ratings")
    book = relationship("Book", back_populates="ratings")

#Recommendation table
class Recommendation(Base):
    __tablename__ = "recommendations"
    
    recommendation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="CASCADE"), nullable=False)
    similarity_score = Column(DECIMAL(5, 4), nullable=False)
    pacing_similarity = Column(DECIMAL(5, 4), nullable=True)
    tone_similarity = Column(DECIMAL(5, 4), nullable=True)
    vocabulary_similarity = Column(DECIMAL(5, 4), nullable=True)
    sentence_length_similarity = Column(DECIMAL(5, 4), nullable=True)
    rank = Column(Integer, nullable=True)
    generated_at = Column(TIMESTAMP, server_default=func.now())
    viewed = Column(Boolean, default=False)
    viewed_at = Column(TIMESTAMP, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="recommendations")
    book = relationship("Book", back_populates="recommendations")
