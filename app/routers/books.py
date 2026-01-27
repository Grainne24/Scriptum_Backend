'''
    This file includes the book end points for managing and importing books and the Gutendex integration - it searches through Project Gutenberg
'''
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models import Book, StylometricProfile
from app.schemas import BookCreate, BookResponse, BookUpdate
from app.services.gutendex_service import gutendex_service

router = APIRouter(prefix="/books", tags=["books"])

#This imports the book metadata from 
@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: UUID, book_update: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    #Update only provided fields
    update_data = book_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(book, key, value)
    
    db.commit()
    db.refresh(book)
    
    return book

@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: UUID, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    db.delete(book)
    db.commit()
    
    return None

@router.get("/analyzed")
def get_analyzed_books(limit: int = 6, db: Session = Depends(get_db)):
    """
    Get books that have been analyzed with their stylometric profiles
    """
    try:
        # Query books that are analyzed and have profiles
        books = db.query(Book).filter(Book.analyzed == True).limit(limit).all()
        
        result = []
        for book in books:
            # Get the stylometric profile
            profile = db.query(StylometricProfile).filter(
                StylometricProfile.book_id == book.book_id
            ).first()
            
            if profile:
                result.append({
                    "book_id": str(book.book_id),
                    "title": book.title,
                    "author": book.author,
                    "publication_year": book.publication_year,
                    "analyzed": book.analyzed,
                    "cover_url": book.cover_url,
                    "pacing_score": float(profile.pacing_score) if profile.pacing_score else None,
                    "tone_score": float(profile.tone_score) if profile.tone_score else None,
                    "vocabulary_richness": float(profile.vocabulary_richness) if profile.vocabulary_richness else None,
                    "avg_sentence_length": float(profile.avg_sentence_length) if profile.avg_sentence_length else None,
                    "avg_word_length": float(profile.avg_word_length) if profile.avg_word_length else None,
                    "lexical_diversity": float(profile.lexical_diversity) if profile.lexical_diversity else None
                })
        
        print(f"Returning {len(result)} analyzed books")
        return result
        
    except Exception as e:
        print(f"Error fetching analyzed books: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch books: {str(e)}"
        )

# This searches gutenberg for a book which a user inputs the name of
@router.get("/search-gutendex")
async def search_gutendex(
    query: Optional[str] = None,
    limit: int = 10
):
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter is required"
        )
    
    try:
        books = await gutendex_service.search_books(
            search=query,
            limit=limit
        )
        return {
            "count": len(books),
            "query": query,
            "books": books
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search Gutendex: {str(e)}"
        )

#This gets book from gutendex by its book ID
@router.post("/import-from-gutendex/{gutenberg_id}", response_model=BookResponse)
async def import_book_from_gutendex(gutenberg_id: int, db: Session = Depends(get_db)):
    """
    Books IDs in Gutendex
    1342 - Pride and Prejudice
    84 - Frankenstein
    """
    try:
        #Get book metadata
        book_data = await gutendex_service.get_book_by_id(gutenberg_id)
        
        if not book_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Book with Gutenberg ID {gutenberg_id} not found"
            )
        
        #Check if already in database
        title = book_data["title"]
        author = book_data["author"]
        cover_url = book_data.get("cover_url")
        
        existing_book = db.query(Book).filter(
            Book.title == title,
            Book.author == author
        ).first()
        
        if existing_book:
            if not existing_book.cover_url and cover_url:
                existing_book.cover_url = cover_url
                db.commit()
                db.refresh(existing_book)
            return existing_book
        
        #Create new book entry
        new_book = Book(
            title=title,
            author=author,
            text_source=f"Project Gutenberg (ID: {gutenberg_id})",
            text_file_path=f"gutenberg_{gutenberg_id}",
            cover_url=cover_url
        )
        
        db.add(new_book)
        db.commit()
        db.refresh(new_book)
        
        return new_book
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import book: {str(e)}"
        )

@router.get("/", response_model=List[BookResponse])
def get_books(
    skip: int = 0, 
    limit: int = 100,
    author: Optional[str] = None,
    analyzed: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Book)
    
    if author:
        query = query.filter(Book.author.ilike(f"%{author}%"))
    
    if analyzed is not None:
        query = query.filter(Book.analyzed == analyzed)
    
    books = query.offset(skip).limit(limit).all()
    return books

@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: UUID, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    return book

#This imports the book metadata from 
@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: UUID, book_update: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    #Update only provided fields
    update_data = book_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(book, key, value)
    
    db.commit()
    db.refresh(book)
    
    return book

@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: UUID, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    db.delete(book)
    db.commit()
    
    return None

@router.get("/analyzed", response_model=List[dict])
def get_analyzed_books(limit: int = 10, db: Session = Depends(get_db)):
    """
    Get books that have been analyzed with their stylometric profiles
    """
    #It will query books that are analyzed and have profiles
    books = db.query(Book).filter(Book.analyzed == True).limit(limit).all()
    
    result = []
    for book in books:
        #This gets the stylometric profile
        profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == book.book_id
        ).first()
        
        if profile:
            result.append({
                "book_id": str(book.book_id),
                "title": book.title,
                "author": book.author,
                "publication_year": book.publication_year,
                "analyzed": book.analyzed,
                "pacing_score": float(profile.pacing_score) if profile.pacing_score else None,
                "tone_score": float(profile.tone_score) if profile.tone_score else None,
                "vocabulary_richness": float(profile.vocabulary_richness) if profile.vocabulary_richness else None,
                "avg_sentence_length": float(profile.avg_sentence_length) if profile.avg_sentence_length else None,
                "avg_word_length": float(profile.avg_word_length) if profile.avg_word_length else None,
                "lexical_diversity": float(profile.lexical_diversity) if profile.lexical_diversity else None
            })
    
    return result
