'''
    This file includes the book end points for managing and importing books and the Gutendex integration - it searches through Project Gutenberg
'''
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime

from app.database import get_db, SessionLocal
from app.models import Book, StylometricProfile, UserBookshelf
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
            if "gutenberg_" in book.text_file_path:
                gutenberg_id = int(book.text_file_path.replace("gutenberg_", ""))
            elif "gutenberg.org/ebooks/" in book.text_file_path:
                #Extract ID from the gutendex URL
                import re
                match = re.search(r'/ebooks/(\d+)', book.text_file_path)
                if match:
                    gutenberg_id = int(match.group(1))
                else:
                    print(f"Could not extract Gutenberg ID from URL: {book.text_file_path}")
                    return
            else:
                print(f"Unknown text_file_path format: {book.text_file_path}")
                return
                
            print(f"Extracted Gutenberg ID: {gutenberg_id}")
        except (ValueError, AttributeError) as e:
            print(f"Failed to extract Gutenberg ID from '{book.text_file_path}': {e}")
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
            "analysis_queued": not bool(db.query(StylometricProfile).filter(
                StylometricProfile.book_id == book_id
            ).first())
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

@router.post("/import-from-gutendex/{gutenberg_id}", response_model=BookResponse)
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

        subjects = book_data.get("subjects", [])
        cleaned_genres = []
        for s in subjects[:5]:
            genre = s.split(" -- ")[0].strip()
            if genre not in cleaned_genres:
                cleaned_genres.append(genre)
        genres_json = json.dumps(cleaned_genres)

        existing_book = db.query(Book).filter(
            Book.title == title,
            Book.author == author
        ).first()

        #Fetch and cache text on import
        text = await gutendex_service.get_book_text(gutenberg_id)

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

@router.post("/bulk-import-gutendex")
async def bulk_import_from_gutendex(
    background_tasks: BackgroundTasks,
    target: int = 6000,
    db: Session = Depends(get_db)
):
    current_count = db.query(Book).count()
    existing_gutenberg_ids = {
        row[0] for row in db.query(Book.gutenberg_id).filter(Book.gutenberg_id.isnot(None)).all()
    }
    background_tasks.add_task(_run_bulk_import, target, existing_gutenberg_ids)
    return {
        "message": f"Bulk import started. Current books: {current_count}, target: {target}",
        "check_logs": "Watch Render logs for progress"
    }

def _run_bulk_import(target: int, existing_gutenberg_ids: set):
    db = SessionLocal()
    imported = 0
    skipped = 0
    page = 1

    try:
        while True:
            current_count = db.query(Book).count()
            if current_count >= target:
                print(f"Bulk import done — reached {current_count} books")
                break

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(gutendex_service.get_books_page(page))
            loop.close()

            results = data.get("results", [])
            if not results:
                print(f"No more results at page {page}")
                break

            for book_data in results:
                gutenberg_id = book_data.get("id")
                if not gutenberg_id or gutenberg_id in existing_gutenberg_ids:
                    skipped += 1
                    continue

                authors_list = book_data.get("authors", [])
                author = authors_list[0].get("name", "Unknown") if authors_list else "Unknown"
                title = book_data.get("title", "Unknown Title")
                formats = book_data.get("formats", {})
                cover_url = formats.get("image/jpeg") or formats.get("image/png")
                subjects = book_data.get("subjects", [])
                cleaned_genres = []
                for s in subjects[:5]:
                    genre = s.split(" -- ")[0].strip()
                    if genre not in cleaned_genres:
                        cleaned_genres.append(genre)

                try:
                    new_book = Book(
                        title=title,
                        author=author,
                        gutenberg_id=gutenberg_id,
                        text_source=f"Project Gutenberg (ID: {gutenberg_id})",
                        text_file_path=f"gutenberg_{gutenberg_id}",
                        cover_url=cover_url,
                        genres=json.dumps(cleaned_genres)
                    )
                    db.add(new_book)
                    db.commit()
                    existing_gutenberg_ids.add(gutenberg_id)
                    imported += 1
                    print(f"Imported [{imported}]: {title} by {author}")
                except Exception as e:
                    db.rollback()
                    skipped += 1
                    print(f"Skipped {title}: {e}")

                current_count = db.query(Book).count()
                if current_count >= target:
                    break

            print(f"Page {page} done — total books: {db.query(Book).count()}, imported: {imported}")
            page += 1
            time.sleep(1)

    except Exception as e:
        print(f"Bulk import error: {e}")
    finally:
        db.close()
        print(f"Bulk import finished — imported: {imported}, skipped: {skipped}")

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
                    subjects = book_data.get("subjects", [])
                    cleaned = []
                    for s in subjects[:5]:
                        genre = s.split(" -- ")[0].strip()
                        if genre not in cleaned:
                            cleaned.append(genre)
                    book.genres = json.dumps(cleaned)
                    db.commit()
                    updated += 1
                    print(f"  Updated: {book.title} → {cleaned}")
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

@router.get("/recommendations/{book_id}")
def get_book_recommendations(
    book_id: UUID,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    try:
        source_book = db.query(Book).filter(Book.book_id == book_id).first()
        if not source_book:
            raise HTTPException(status_code=404, detail="Book not found")

        source_profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == book_id
        ).first()

        if not source_profile:
            raise HTTPException(status_code=400, detail="Source book hasn't been analyzed yet")

        #Get all the other analysed books with profiles
        candidates = db.query(Book, StylometricProfile).join(
            StylometricProfile, Book.book_id == StylometricProfile.book_id
        ).filter(
            Book.book_id != book_id,
            Book.analysed == True
        ).all()

        if not candidates:
            return {"source_book": {"book_id": source_book.book_id, "title": source_book.title, "author": source_book.author}, "recommendations": []}

        #Score by euclidean distance across stylometric features
        scored = []
        for book, profile in candidates:
            try:
                diff = (
                    (float(source_profile.pacing_score or 0) - float(profile.pacing_score or 0)) ** 2 +
                    (float(source_profile.tone_score or 0) - float(profile.tone_score or 0)) ** 2 +
                    (float(source_profile.vocabulary_richness or 0) - float(profile.vocabulary_richness or 0)) ** 2 +
                    (float(source_profile.avg_sentence_length or 0) - float(profile.avg_sentence_length or 0)) ** 2
                )
                similarity = 1 / (1 + diff ** 0.5)

                scored.append({
                    "book_id": book.book_id,
                    "title": book.title,
                    "author": book.author,
                    "similarity_score": round(similarity, 4),
                    "cover_url": book.cover_url,
                    "summary": book.summary,
                    "pacing_score": float(profile.pacing_score or 0),
                    "tone_score": float(profile.tone_score or 0),
                    "vocabulary_richness": float(profile.vocabulary_richness or 0)
                })
            except Exception as e:
                print(f"Error scoring {book.title}: {e}")
                continue

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)

        return {
            "source_book": {
                "book_id": source_book.book_id,
                "title": source_book.title,
                "author": source_book.author
            },
            "recommendations": scored[:limit],
            "cached": False
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in recommendations endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {str(e)}")

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