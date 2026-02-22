from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Book, UserBookshelf, Recommendation
from app.services.stylometry_service import stylometry_analyser
from app.services.gutendex_service import gutendex_service
from pydantic import BaseModel
from typing import List
from uuid import UUID
import uuid
from datetime import datetime

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

class RecommendationResponse(BaseModel):
    book_id: UUID
    title: str
    author: str
    cover_url: str | None
    delta: float
    similarity: float

    model_config = {"from_attributes": True}


@router.get("/for-user/{user_id}", response_model=List[RecommendationResponse])
async def get_recommendations_for_user(user_id: UUID, limit: int = 10, db: Session = Depends(get_db)):
    try:
        #Get user's bookshelf
        user_books = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_id
        ).all()

        if not user_books:
            raise HTTPException(status_code=404, detail="User has no books on their bookshelf")

        shelf_book_ids = [ub.book_id for ub in user_books]

        #Get shelf books that have cached text
        shelf_books = db.query(Book).filter(
            Book.book_id.in_(shelf_book_ids),
            Book.text_content != None
        ).all()

        #Fallback: if no cached text, try fetching live from Gutenberg
        if not shelf_books:
            shelf_books_no_text = db.query(Book).filter(
                Book.book_id.in_(shelf_book_ids),
                Book.gutenberg_id != None
            ).all()

            if not shelf_books_no_text:
                raise HTTPException(status_code=400, detail="No Gutenberg books found on shelf. Add books from the search page.")

            print("No cached text found for shelf books, fetching from Gutenberg...")
            for book in shelf_books_no_text:
                text = await gutendex_service.get_book_text(book.gutenberg_id)
                if text:
                    book.text_content = text[:150000]
            db.commit()

            shelf_books = db.query(Book).filter(
                Book.book_id.in_(shelf_book_ids),
                Book.text_content != None
            ).all()

        if not shelf_books:
            raise HTTPException(status_code=400, detail="Could not fetch text for your shelf books")

        #Get candidate books with cached text (not on shelf)
        candidates = db.query(Book).filter(
            Book.book_id.notin_(shelf_book_ids),
            Book.text_content != None
        ).limit(20).all()

        #Fallback: fetch live if no cached candidates
        if not candidates:
            candidates_no_text = db.query(Book).filter(
                Book.book_id.notin_(shelf_book_ids),
                Book.gutenberg_id != None
            ).limit(10).all()

            if not candidates_no_text:
                raise HTTPException(status_code=404, detail="No candidate books found. Import more books.")

            print("No cached candidates, fetching from Gutenberg...")
            for book in candidates_no_text:
                text = await gutendex_service.get_book_text(book.gutenberg_id)
                if text:
                    book.text_content = text[:150000]
            db.commit()

            candidates = db.query(Book).filter(
                Book.book_id.notin_(shelf_book_ids),
                Book.text_content != None
            ).limit(20).all()

        if not candidates:
            raise HTTPException(status_code=404, detail="Could not get text for candidate books")

        #Build shelf texts from cached content — no Gutenberg calls needed
        shelf_texts = [book.text_content for book in shelf_books]
        print(f"Using cached text for {len(shelf_texts)} shelf books")

        candidate_list = [
            {
                "author": book.author,
                "title": book.title,
                "text": book.text_content,
                "book_id": str(book.book_id)
            }
            for book in candidates
        ]
        print(f"Using cached text for {len(candidate_list)} candidate books")

        #Build seed from combined shelf texts
        combined_user_text = " ".join(shelf_texts)
        seed = {
            "author": "User Profile",
            "title": "User Bookshelf",
            "text": combined_user_text
        }

        #Run Burrows' Delta
        results = stylometry_analyser.get_recommendations(seed, candidate_list, top_n=limit)

        #Map results back to book objects and save to recommendations table
        title_to_book = {b.title: b for b in candidates}
        response = []

        #Clear old recommendations for this user
        db.query(Recommendation).filter(Recommendation.user_id == user_id).delete()

        for rank, r in enumerate(results, start=1):
            book = title_to_book.get(r["title"])
            if book:
                rec = Recommendation(
                    recommendation_id=uuid.uuid4(),
                    user_id=user_id,
                    book_id=book.book_id,
                    similarity_score=r["similarity"],
                    rank=rank,
                    generated_at=datetime.utcnow()
                )
                db.add(rec)

                response.append(RecommendationResponse(
                    book_id=book.book_id,
                    title=book.title,
                    author=book.author,
                    cover_url=book.cover_url,
                    delta=r["delta"],
                    similarity=r["similarity"]
                ))

        db.commit()
        print(f"Saved {len(response)} recommendations for user {user_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"RECOMMENDATION ERROR: {str(e)}")
        print(traceback.format_exc())
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")

@router.get("/{book_id}", response_model=List[RecommendationResponse])
def get_recommendations(book_id: UUID, limit: int = 10, db: Session = Depends(get_db)):

    seed_book = db.query(Book).filter(Book.book_id == book_id).first()
    if not seed_book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not seed_book.text_source:
        raise HTTPException(status_code=400, detail="Seed book has no text available")

    candidates = db.query(Book).filter(
        Book.book_id != book_id,
        Book.analysed == True,
        Book.text_source != None
    ).limit(500).all()

    if not candidates:
        raise HTTPException(status_code=404, detail="No candidate books found")

    seed = {
        "author": seed_book.author,
        "title": seed_book.title,
        "text": seed_book.text_source
    }
    candidate_list = [
        {"author": b.author, "title": b.title, "text": b.text_source, "book_id": str(b.book_id)}
        for b in candidates
    ]

    results = stylometry_analyser.get_recommendations(seed, candidate_list, top_n=limit)

    title_to_book = {b.title: b for b in candidates}
    response = []
    for r in results:
        book = title_to_book.get(r["title"])
        if book:
            response.append(RecommendationResponse(
                book_id=book.book_id,
                title=book.title,
                author=book.author,
                cover_url=book.cover_url,
                delta=r["delta"],
                similarity=r["similarity"]
            ))

    return response