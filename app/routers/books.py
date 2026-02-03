'''
    This file includes the book end points for managing and importing books and the Gutendex integration - it searches through Project Gutenberg
'''
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date

from app.database import get_db
from app.models import Book, StylometricProfile, UserBookshelf, UserBookshelfUpdate
from app.schemas import BookResponse, BookUpdate
from app.services.gutendex_service import gutendex_service

router = APIRouter(prefix="/books", tags=["books"])

'''
    This holds all the users information in their personal bookshelf - this will hold the saved and favorited books in the bookshelf
'''

@router.get("/user-bookshelf", response_model=List[BookResponse])
def get_my_bookshelf(
    user_id: str, 
    limit: int = 100,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        #This joins books with user_bookshelf table to get only user's saved books
        books = db.query(Book, UserBookshelf).join(
            UserBookshelf, Book.book_id == UserBookshelf.book_id
        ).filter(
            UserBookshelf.user_id == user_uuid
        ).limit(limit).all()
        
        result = []
        for book, bookshelf_entry in books:
            profile = db.query(StylometricProfile).filter(
                StylometricProfile.book_id == book.book_id
            ).first()
            
            result.append({
                "book_id": book.book_id,
                "title": book.title,
                "author": book.author,
                "publication_year": book.publication_year,
                "created_at": book.created_at,
                "analysed": book.analysed if book.analysed is not None else False,
                "cover_url": book.cover_url,
                "summary": book.summary,
                "text_source": book.text_source,
                "book_status": bookshelf_entry.book_status,
                "comments": bookshelf_entry.comments,
                "date_started": bookshelf_entry.date_started,
                "date_ended": bookshelf_entry.date_ended,
                "pacing_score": float(profile.pacing_score) if profile and profile.pacing_score else None,
                "tone_score": float(profile.tone_score) if profile and profile.tone_score else None,
                "vocabulary_richness": float(profile.vocabulary_richness) if profile and profile.vocabulary_richness else None,
                "avg_sentence_length": float(profile.avg_sentence_length) if profile and profile.avg_sentence_length else None,
                "avg_word_length": float(profile.avg_word_length) if profile and profile.avg_word_length else None,
                "lexical_diversity": float(profile.lexical_diversity) if profile and profile.lexical_diversity else None
            })
        
        print(f"Returning {len(result)} books from user's bookshelf")
        return result
        
    except Exception as e:
        print(f"Error fetching user bookshelf: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bookshelf: {str(e)}"
        )
    
@router.get("/my-bookshelf/{book_id}", response_model=BookResponse)
def get_bookshelf_book_details(
    book_id: UUID,
    user_id: str,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        # Join to get both book and bookshelf data
        result = db.query(Book, UserBookshelf).join(
            UserBookshelf, Book.book_id == UserBookshelf.book_id
        ).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.book_id == book_id
        ).first()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not found in your bookshelf"
            )
        
        book, bookshelf_entry = result
        
        profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == book.book_id
        ).first()
        
        return {
            "book_id": book.book_id,
            "title": book.title,
            "author": book.author,
            "publication_year": book.publication_year,
            "created_at": book.created_at,
            "analysed": book.analysed if book.analysed is not None else False,
            "cover_url": book.cover_url,
            "summary": book.summary,
            "text_source": book.text_source,
            "book_status": bookshelf_entry.book_status,
            "comments": bookshelf_entry.comments,
            "date_started": bookshelf_entry.date_started,
            "date_ended": bookshelf_entry.date_ended,
            "pacing_score": float(profile.pacing_score) if profile and profile.pacing_score else None,
            "tone_score": float(profile.tone_score) if profile and profile.tone_score else None,
            "vocabulary_richness": float(profile.vocabulary_richness) if profile and profile.vocabulary_richness else None,
            "avg_sentence_length": float(profile.avg_sentence_length) if profile and profile.avg_sentence_length else None,
            "avg_word_length": float(profile.avg_word_length) if profile and profile.avg_word_length else None,
            "lexical_diversity": float(profile.lexical_diversity) if profile and profile.lexical_diversity else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching bookshelf book details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch book details: {str(e)}"
        )

@router.post("/my-bookshelf/{book_id}")
def add_to_bookshelf(
    book_id: UUID,
    user_id: str, 
    book_status: str = "want_to_read",
    comments: Optional[str] = None,
    date_started: Optional[date] = None,
    date_ended: Optional[date] = None,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        #Check if its already in the bookshelf
        existing = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.book_id == book_id
        ).first()
        
        if existing:
            existing.book_status = book_status
            existing.comments = comments
            existing.date_started = date_started
            existing.date_ended = date_ended
            db.commit()
            return {"message": "Book status updated"}
        
        #Verify the book exists
        book = db.query(Book).filter(Book.book_id == book_id).first()
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not found"
            )
        
        #Add to the bookshelf
        bookshelf_entry = UserBookshelf(
            user_id=user_uuid,
            book_id=book_id,
            book_status=book_status,
            comments=comments,
            date_started=date_started,
            date_ended=date_ended
        )
        
        db.add(bookshelf_entry)
        db.commit()
        
        return {"message": "Book added to bookshelf successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add book: {str(e)}"
        )
    
@router.put("/my-bookshelf/{book_id}")
def update_bookshelf_entry(
    book_id: UUID,
    user_id: str,
    update_data: UserBookshelfUpdate,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        bookshelf_entry = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.book_id == book_id
        ).first()
        
        if not bookshelf_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not in bookshelf"
            )
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(bookshelf_entry, key, value)
        
        db.commit()
        db.refresh(bookshelf_entry)
        
        return {
            "message": "Bookshelf entry updated successfully",
            "book_status": bookshelf_entry.book_status,
            "comments": bookshelf_entry.comments,
            "date_started": bookshelf_entry.date_started,
            "date_ended": bookshelf_entry.date_ended
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update bookshelf entry: {str(e)}"
        )
    
@router.put("/my-bookshelf/{book_id}/status")
def update_book_status(
    book_id: UUID,
    user_id: str,
    book_status: str,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        bookshelf_entry = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.book_id == book_id
        ).first()
        
        if not bookshelf_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not in bookshelf"
            )
        bookshelf_entry.book_status = book_status
        db.commit()
        
        return {"message": f"Book status updated to {book_status}"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update status: {str(e)}"
        )

@router.delete("/my-bookshelf/{book_id}")
def remove_from_bookshelf(
    book_id: UUID,
    user_id: str,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        bookshelf_entry = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.book_id == book_id
        ).first()
        
        if not bookshelf_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not in bookshelf"
            )
        
        db.delete(bookshelf_entry)
        db.commit()
        
        return {"message": "Book removed from bookshelf"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove book: {str(e)}"
        )

'''
    This is used for the search page and searched all the books in the database
'''
@router.get("/search", response_model=List[BookResponse])
def search_all_books(
    query: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    try:
        #First start with books that have summaries
        books_query = db.query(Book).filter(Book.summary.isnot(None))
        
        #Then if the user typed a search query, filter by title or author
        if query:
            books_query = books_query.filter(
                (Book.title.ilike(f"%{query}%")) | 
                (Book.author.ilike(f"%{query}%"))
            )
        
        books = books_query.limit(limit).all()
        
        result = []
        for book in books:
            profile = db.query(StylometricProfile).filter(
                StylometricProfile.book_id == book.book_id
            ).first()
            
            result.append({
                "book_id": book.book_id,
                "title": book.title,
                "author": book.author,
                "publication_year": book.publication_year,
                "created_at": book.created_at,
                "analysed": book.analysed if book.analysed is not None else False,
                "cover_url": book.cover_url,
                "summary": book.summary,
                "text_source": book.text_source,
                "pacing_score": float(profile.pacing_score) if profile and profile.pacing_score else None,
                "tone_score": float(profile.tone_score) if profile and profile.tone_score else None,
                "vocabulary_richness": float(profile.vocabulary_richness) if profile and profile.vocabulary_richness else None,
                "avg_sentence_length": float(profile.avg_sentence_length) if profile and profile.avg_sentence_length else None,
                "avg_word_length": float(profile.avg_word_length) if profile and profile.avg_word_length else None,
                "lexical_diversity": float(profile.lexical_diversity) if profile and profile.lexical_diversity else None
            })
        
        print(f"Search returned {len(result)} books")
        return result
        
    except Exception as e:
        print(f"Error searching books: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search books: {str(e)}"
        )
'''
    This is kept for testing
'''
@router.get("/bookshelf", response_model=List[BookResponse])
@router.get("/analyzed", response_model=List[BookResponse])
def get_bookshelf_books(limit: int = 10, db: Session = Depends(get_db)):
    try:
        books = db.query(Book).filter(Book.summary.isnot(None)).limit(limit).all()
        
        result = []
        for book in books:
            profile = db.query(StylometricProfile).filter(
                StylometricProfile.book_id == book.book_id
            ).first()
            
            result.append({
                "book_id": book.book_id,
                "title": book.title,
                "author": book.author,
                "publication_year": book.publication_year,
                "created_at": book.created_at,
                "analysed": book.analysed if book.analysed is not None else False,
                "cover_url": book.cover_url,
                "summary": book.summary,
                "text_source": book.text_source,
                "pacing_score": float(profile.pacing_score) if profile and profile.pacing_score else None,
                "tone_score": float(profile.tone_score) if profile and profile.tone_score else None,
                "vocabulary_richness": float(profile.vocabulary_richness) if profile and profile.vocabulary_richness else None,
                "avg_sentence_length": float(profile.avg_sentence_length) if profile and profile.avg_sentence_length else None,
                "avg_word_length": float(profile.avg_word_length) if profile and profile.avg_word_length else None,
                "lexical_diversity": float(profile.lexical_diversity) if profile and profile.lexical_diversity else None
            })
        
        return result
        
    except Exception as e:
        print(f"Error fetching bookshelf books: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch books: {str(e)}"
        )
    
'''
    This searches through gutendex for results
'''
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

@router.get("/", response_model=List[BookResponse])
def get_books(
    skip: int = 0, 
    limit: int = 100,
    author: Optional[str] = None,
    analysed: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Book)
    
    if author:
        query = query.filter(Book.author.ilike(f"%{author}%"))
    
    if analysed is not None:
        query = query.filter(Book.analysed == analysed)
    
    books = query.offset(skip).limit(limit).all()
    return books

@router.post("/import-from-gutendex/{gutenberg_id}", response_model=BookResponse)
async def import_book_from_gutendex(gutenberg_id: int, db: Session = Depends(get_db)):
    """
    Books IDs in Gutendex
    1342 - Pride and Prejudice
    84 - Frankenstein
    """
    try:
        book_data = await gutendex_service.get_book_by_id(gutenberg_id)
        
        if not book_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Book with Gutenberg ID {gutenberg_id} not found"
            )
        
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

@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: UUID, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    return book

@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: UUID, book_update: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.book_id == book_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
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