'''
    This file includes the book end points for managing and importing books and the Gutendex integration - it searches through Project Gutenberg
'''
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime

from app.database import get_db, SessionLocal
from app.models import Book, StylometricProfile, UserBookshelf, BookSimilarity, Rating
from app.schemas import BookResponse, BookUpdate, UserBookshelfUpdate
from app.services.gutendex_service import gutendex_service
from app.services.stylometry_service import stylometry_analyser

import asyncio
import json
import time

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
        
        #This joins books with user_bookshelf table to get only user's books in their bookshelf
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
                "rating": float(bookshelf_entry.rating) if bookshelf_entry.rating else None,
                "rated_at": str(bookshelf_entry.rated_at) if bookshelf_entry.rated_at else None,
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
        
        #Join to get both the book and the bookshelf data
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
    
def analyse_book_background(book_id: UUID):
    print(f"Task started for book {book_id}")
    db = SessionLocal()
    
    try:
        #Check if the book has already been analyzed
        existing_profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == book_id
        ).first()
        
        if existing_profile:
            print(f"Book {book_id} already analyzed, skipping")
            return
        
        #Get the book details
        book = db.query(Book).filter(Book.book_id == book_id).first()
        if not book:
            print(f"Book {book_id} not found in database")
            return
            
        if not book.text_file_path:
            print(f"Book {book_id} has no text_file_path")
            return
        
        print(f"Found book: '{book.title}' by {book.author}")
        print(f"Text file path: {book.text_file_path}")

        try:
            gutenberg_id = extract_gutenberg_id(book.text_file_path)
            print(f"Extracted Gutenberg ID: {gutenberg_id}")
        except ValueError as e:
            print(f"Failed to extract Gutenberg ID: {e}")
            return
        
        #Fetch the full text of the book from Gutenberg
        print(f"Fetching text from Gutenberg API...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        text = loop.run_until_complete(gutendex_service.get_book_text(gutenberg_id))
        if text:
            text = text[:50000]  #Only need first 50k chars for stylometry
        loop.close()
        
        if not text:
            print(f"ERROR: Could not fetch text for Gutenberg ID {gutenberg_id}")
            return
        
        print(f"Fetched {len(text)} characters")
        
        #Analyze the text of the book
        print(f"Starting stylometric analysis...")
        analysis_results = stylometry_analyser.analyse_text(text)
        print(f"Analysis complete: {analysis_results}")
        
        #Finally, create the stylometric profile for the book
        profile = StylometricProfile(
            book_id=book_id,
            pacing_score=analysis_results["pacing_score"],
            tone_score=analysis_results["tone_score"],
            vocabulary_richness=analysis_results["vocabulary_richness"],
            avg_sentence_length=analysis_results["avg_sentence_length"],
            avg_word_length=analysis_results["avg_word_length"],
            lexical_diversity=analysis_results["lexical_diversity"],
            total_words=analysis_results["total_words"],
            total_sentences=analysis_results["total_sentences"],
            unique_words=analysis_results["unique_words"],
            analysis_version="1.0"
        )
        
        if hasattr(StylometricProfile, 'punctuation_density'):
            profile.punctuation_density = analysis_results.get("punctuation_density")
        if hasattr(StylometricProfile, 'dialogue_percentage'):
            profile.dialogue_percentage = analysis_results.get("dialogue_percentage")
        
        print(f"Adding profile to database...")
        db.add(profile)
        book.analysed = True
        
        print(f"Committing to database...")
        db.commit()
        
        print(f"Successfully analyzed and saved book {book_id}")
        
    except Exception as e:
        db.rollback()
        print(f"Analysis failed for book {book_id}: {str(e)}")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
    finally:
        db.close()
        print(f"Database session closed for book {book_id}")

@router.post("/my-bookshelf/{book_id}")
async def add_to_bookshelf(
    book_id: UUID,
    user_id: str,
    background_tasks: BackgroundTasks, 
    book_status: str = "want_to_read",
    comments: Optional[str] = None,
    date_started: Optional[date] = None,
    date_ended: Optional[date] = None,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        
        #Check if it's already in the bookshelf
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
        
        #Verify the book already exists
        book = db.query(Book).filter(Book.book_id == book_id).first()
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not found"
            )
        
        #Add the book to the bookshelf
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
        
        #Trigger the background analysis if the book hasn't been analysed yet
        if background_tasks:
            existing_profile = db.query(StylometricProfile).filter(
                StylometricProfile.book_id == book_id
            ).first()
            
            if not existing_profile:
                background_tasks.add_task(
                    analyse_book_background, 
                    book_id
                )
                print(f"Queued background analysis for book {book_id}")
        
        return {
            "message": "Book added to bookshelf successfully",
            "analysis_queued": not bool(existing_profile)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add book: {str(e)}"
        )
    

@router.post("/my-bookshelf/{book_id}/rating")
def save_book_rating(
    book_id: UUID,
    user_id: str,
    rating: float,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
        bookshelf_entry = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.book_id == book_id
        ).first()

        if not bookshelf_entry:
            raise HTTPException(status_code=404, detail="Book not in bookshelf")

        bookshelf_entry.rating = rating
        bookshelf_entry.rated_at = datetime.utcnow()
        bookshelf_entry.updated_at = datetime.utcnow()
        db.commit()

        print(f"Saved rating {rating} for book {book_id}")
        return {"message": f"Rating saved: {rating}"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error saving rating: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save rating: {str(e)}")
    
    
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

        if update_data.book_status is not None:
            bookshelf_entry.book_status = update_data.book_status
        if update_data.comments is not None:
            bookshelf_entry.comments = update_data.comments
        if update_data.date_started is not None:
            bookshelf_entry.date_started = update_data.date_started
        if update_data.date_ended is not None:
            bookshelf_entry.date_ended = update_data.date_ended

        db.commit()
        db.refresh(bookshelf_entry)

        print(f"Updated bookshelf entry for book {book_id}: status={bookshelf_entry.book_status}, comments={bookshelf_entry.comments}")

        return {
            "message": "Bookshelf entry updated successfully",
            "book_status": bookshelf_entry.book_status,
            "comments": bookshelf_entry.comments,
            "date_started": str(bookshelf_entry.date_started) if bookshelf_entry.date_started else None,
            "date_ended": str(bookshelf_entry.date_ended) if bookshelf_entry.date_ended else None
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error updating bookshelf entry: {str(e)}")
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
@router.get("/analysed", response_model=List[BookResponse])
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

def _parse_genres(subjects: list) -> str:
    cleaned = []
    for s in subjects[:5]:
        genre = s.split(" -- ")[0].strip()
        if genre not in cleaned:
            cleaned.append(genre)
    return json.dumps(cleaned)
    
async def import_book_from_gutendex(gutenberg_id: int, db: Session = Depends(get_db)):
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

        genres_json = _parse_genres(book_data.get("subjects", []))

        new_book = Book(
            title=title,
            author=author,
            gutenberg_id=gutenberg_id,
            text_source=f"Project Gutenberg (ID: {gutenberg_id})",
            text_file_path=f"gutenberg_{gutenberg_id}",
            cover_url=cover_url,
            genres=genres_json 
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

@router.post("/backfill-genres")
async def backfill_genres(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    books = db.query(Book).filter(
        Book.gutenberg_id.isnot(None),
        Book.genres.is_(None)
    ).all()

    book_ids = [book.book_id for book in books]
    print(f"Queuing genre backfill for {len(book_ids)} books")

    background_tasks.add_task(run_genre_backfill, book_ids)

    return {
        "message": f"Genre backfill started for {len(book_ids)} books",
        "check_logs": "Watch Render logs for progress"
    }

def run_genre_backfill(book_ids: list):

    db = SessionLocal()
    updated = 0
    failed = 0

    try:
        for book_id in book_ids:
            try:
                book = db.query(Book).filter(Book.book_id == book_id).first()
                if not book or not book.gutenberg_id:
                    continue

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                book_data = loop.run_until_complete(
                    gutendex_service.get_book_by_id(book.gutenberg_id)
                )
                loop.close()

                if book_data:
                    book.genres = _parse_genres(book_data.get("subjects", []))
                    db.commit()
                    updated += 1
                else:
                    failed += 1

                time.sleep(1)

            except Exception as e:
                failed += 1
                print(f"  Failed: {e}")
                db.rollback()
                time.sleep(2)
                continue

    finally:
        db.close()
        print(f"Genre backfill done — {updated} updated, {failed} failed")
@router.post("/bulk-analyse")
def bulk_analyse_books(
    limit: int = 50,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    books_to_analyse = db.query(Book).filter(
        Book.text_file_path.isnot(None),
        (Book.analysed == False) | (Book.analysed.is_(None))
    ).limit(limit).all()

    print(f"Found {len(books_to_analyse)} books to analyse")

    queued = []
    for book in books_to_analyse:
        background_tasks.add_task(analyse_book_background, book.book_id)
        queued.append(book.title)

    return {
        "message": f"Queued {len(queued)} books for analysis",
        "queued": queued
    }

@router.get("/{book_id}/stylometric-profile")
def get_stylometric_profile(
    book_id: UUID,
    db: Session = Depends(get_db)
):
    try:
        profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == book_id
        ).first()

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stylometric profile not found for this book"
            )

        return {
            "pacing_score":        float(profile.pacing_score or 0),
            "tone_score":          float(profile.tone_score or 0),
            "vocabulary_richness": float(profile.vocabulary_richness or 0),
            "avg_sentence_length": float(profile.avg_sentence_length or 0),
            "avg_word_length":     float(profile.avg_word_length or 0),
            "lexical_diversity":   float(profile.lexical_diversity or 0),
            "punctuation_density": float(profile.punctuation_density or 0) if profile.punctuation_density else 0.0,
            "dialogue_percentage": float(profile.dialogue_percentage or 0) if profile.dialogue_percentage else 0.0,
            "total_words":         profile.total_words or 0,
            "total_sentences":     profile.total_sentences or 0,
            "unique_words":        profile.unique_words or 0
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching stylometric profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch stylometric profile: {str(e)}"
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

def extract_gutenberg_id(text_file_path: str) -> int:
    """Extract Gutenberg ID from text_file_path"""
    if "gutenberg_" in text_file_path:
        return int(text_file_path.replace("gutenberg_", ""))
    elif "gutenberg.org/ebooks/" in text_file_path:
        import re
        match = re.search(r'/ebooks/(\d+)', text_file_path)
        if match:
            return int(match.group(1))
    raise ValueError(f"Cannot extract Gutenberg ID from: {text_file_path}")

@router.get("/recommendations/{book_id}")
async def get_book_recommendations(
    book_id: UUID,
    limit: int = 10,
    force_recalculate: bool = False, 
    db: Session = Depends(get_db)
):
    try:
        print(f"Getting recommendations for book {book_id}")
        
        #Get the source book
        source_book = db.query(Book).filter(Book.book_id == book_id).first()
        if not source_book:
            raise HTTPException(status_code=404, detail="Book not found")
        
        source_profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == book_id
        ).first()
        
        if not source_profile:
            raise HTTPException(
                status_code=400,
                detail="Source book hasn't been analyzed yet"
            )
        
        #first it checks if the similarities of the two books are already stored
        if not force_recalculate:
            existing_similarities = db.query(BookSimilarity).filter(
                (BookSimilarity.book_id_1 == book_id) | 
                (BookSimilarity.book_id_2 == book_id)
            ).order_by(BookSimilarity.similarity_score.desc()).limit(limit).all()
            
            if len(existing_similarities) >= limit:
                print(f"Found {len(existing_similarities)} cached similarities")
                
                #Convert to response format
                recommendations = []
                for sim in existing_similarities:
                    #Get the other book which the book is being compared to
                    other_book_id = sim.book_id_2 if sim.book_id_1 == book_id else sim.book_id_1
                    
                    other_book = db.query(Book, StylometricProfile).join(
                        StylometricProfile
                    ).filter(Book.book_id == other_book_id).first()
                    
                    if other_book:
                        book, profile = other_book
                        recommendations.append({
                            "book_id": book.book_id,
                            "title": book.title,
                            "author": book.author,
                            "similarity_score": round(sim.similarity_score, 4),
                            "pacing_similarity": round(sim.pacing_similarity, 4) if sim.pacing_similarity else None,
                            "tone_similarity": round(sim.tone_similarity, 4) if sim.tone_similarity else None,
                            "vocabulary_similarity": round(sim.vocabulary_similarity, 4) if sim.vocabulary_similarity else None,
                            "cover_url": book.cover_url,
                            "summary": book.summary,
                            "pacing_score": float(profile.pacing_score),
                            "tone_score": float(profile.tone_score),
                            "vocabulary_richness": float(profile.vocabulary_richness)
                        })
                
                return {
                    "source_book": {
                        "book_id": source_book.book_id,
                        "title": source_book.title,
                        "author": source_book.author
                    },
                    "recommendations": recommendations,
                    "cached": True
                }
        
        #Then calculate two new books and their similarities
        print("Calculating new similarities...")
        
        #Filter candidates by similar features
        pacing_range = 20
        tone_range = 20
        vocab_range = 10
        
        candidate_books = db.query(Book, StylometricProfile).join(
            StylometricProfile
        ).filter(
            Book.book_id != book_id,
            Book.analysed == True,
            StylometricProfile.pacing_score.between(
                source_profile.pacing_score - pacing_range,
                source_profile.pacing_score + pacing_range
            ),
            StylometricProfile.tone_score.between(
                source_profile.tone_score - tone_range,
                source_profile.tone_score + tone_range
            ),
            StylometricProfile.vocabulary_richness.between(
                source_profile.vocabulary_richness - vocab_range,
                source_profile.vocabulary_richness + vocab_range
            )
        ).limit(100).all()
        
        print(f"Found {len(candidate_books)} candidates")
        
        #Get source book text
        source_gutenberg_id = extract_gutenberg_id(source_book.text_file_path)
        source_text = await gutendex_service.get_book_text(source_gutenberg_id)
        
        if not source_text:
            raise HTTPException(status_code=500, detail="Could not fetch source text")
        
        #Calculate and store the similarities
        similarities = []
        for book, profile in candidate_books[:50]:
            try:
                candidate_gutenberg_id = extract_gutenberg_id(book.text_file_path)
                candidate_text = await gutendex_service.get_book_text(candidate_gutenberg_id)
                
                if not candidate_text:
                    continue
                
                #Calculate Burrows' Delta
                similarity = stylometry_analyser.calculate_similarity(source_text, candidate_text)
                
                #Calculate feature similarities
                feature_sims = stylometry_analyser.calculate_normalized_similarity(source_profile, profile, db)
                pacing_sim = feature_sims["pacing_similarity"]
                tone_sim = feature_sims["tone_similarity"]
                vocab_sim = feature_sims["vocabulary_similarity"]
                sent_sim = feature_sims["sentence_length_similarity"]

                #store it in the database
                book_id_1 = min(book_id, book.book_id)
                book_id_2 = max(book_id, book.book_id)
                
                #Check if already exists
                existing = db.query(BookSimilarity).filter(
                    BookSimilarity.book_id_1 == book_id_1,
                    BookSimilarity.book_id_2 == book_id_2
                ).first()
                
                if not existing:
                    new_similarity = BookSimilarity(
                        book_id_1=book_id_1,
                        book_id_2=book_id_2,
                        similarity_score=similarity,
                        pacing_similarity=pacing_sim,
                        tone_similarity=tone_sim,
                        vocabulary_similarity=vocab_sim,
                        sentence_length_similarity=sent_sim
                    )
                    db.add(new_similarity)
                
                similarities.append({
                    "book_id": book.book_id,
                    "title": book.title,
                    "author": book.author,
                    "similarity_score": round(similarity, 4),
                    "pacing_similarity": round(pacing_sim, 4),
                    "tone_similarity": round(tone_sim, 4),
                    "vocabulary_similarity": round(vocab_sim, 4),
                    "cover_url": book.cover_url,
                    "summary": book.summary,
                    "pacing_score": float(profile.pacing_score),
                    "tone_score": float(profile.tone_score),
                    "vocabulary_richness": float(profile.vocabulary_richness)
                })
                
            except Exception as e:
                print(f"Error processing {book.title}: {e}")
                continue
        
        #Commit all new similarities
        db.commit()
        
        #Sort and return
        similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return {
            "source_book": {
                "book_id": source_book.book_id,
                "title": source_book.title,
                "author": source_book.author
            },
            "recommendations": similarities[:limit],
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in recommendations endpoint: {str(e)}")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(e)}"
        )
    
