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
from app.feedback_weights import calculate_feedback_adjustment

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

class RecommendationResponse(BaseModel):
    book_id: UUID
    title: str
    author: str
    cover_url: str | None
    delta: float
    similarity: float

    model_config = {"from_attributes": True}


@router.get("/for-user/{user_id}")
def get_recommendations_for_user(
    user_id: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)

        rated_entries = db.query(UserBookshelf).filter(
            UserBookshelf.user_id == user_uuid,
            UserBookshelf.rating.isnot(None)
        ).all()

        user_rated_books = []
        for entry in rated_entries:
            profile = db.query(StylometricProfile).filter(
                StylometricProfile.book_id == entry.book_id
            ).first()
            if profile:
                user_rated_books.append((profile, float(entry.rating)))

        print(f"User has rated {len(user_rated_books)} books with profiles")

        shelf_book_ids = set(
            entry.book_id for entry in db.query(UserBookshelf).filter(
                UserBookshelf.user_id == user_uuid
            ).all()
        )

        candidates = db.query(Book, StylometricProfile).join(
            StylometricProfile, Book.book_id == StylometricProfile.book_id
        ).filter(
            Book.analysed == True,
            ~Book.book_id.in_(shelf_book_ids)
        ).all()

        print(f"Found {len(candidates)} candidate books to rank")

        if not candidates:
            return []

        scored = []

        for book, profile in candidates:
            base_score = 0.5

            for entry in rated_entries:
                book_id_1 = min(entry.book_id, book.book_id)
                book_id_2 = max(entry.book_id, book.book_id)

                cached_sim = db.query(BookSimilarity).filter(
                    BookSimilarity.book_id_1 == book_id_1,
                    BookSimilarity.book_id_2 == book_id_2
                ).first()

                if cached_sim:
                    base_score = max(base_score, cached_sim.similarity_score)

            feedback_adj = calculate_feedback_adjustment(profile, user_rated_books)

            final_score = (base_score * 2) + feedback_adj 

            scored.append({
                "book_id": str(book.book_id),
                "title": book.title,
                "author": book.author,
                "cover_url": book.cover_url,
                "summary": book.summary,
                "delta": round(base_score, 4),
                "similarity": round(final_score, 4),
                "feedback_adjustment": round(feedback_adj, 4),
                "pacing_score": float(profile.pacing_score) if profile.pacing_score else None,
                "tone_score": float(profile.tone_score) if profile.tone_score else None,
                "vocabulary_richness": float(profile.vocabulary_richness) if profile.vocabulary_richness else None,
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)

        print(f"Returning top {limit} recommendations")
        return scored[:limit]

    except Exception as e:
        print(f"Error getting recommendations: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recommendations: {str(e)}"
        )

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