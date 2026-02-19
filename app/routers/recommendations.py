from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Book
from app.routers.stylometry import stylometry_analyser
from pydantic import BaseModel
from typing import List
from uuid import UUID

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

class RecommendationResponse(BaseModel):
    book_id: UUID
    title: str
    author: str
    cover_url: str | None
    delta: float
    similarity: float

    model_config = {"from_attributes": True}

@router.get("/{book_id}", response_model=List[RecommendationResponse])
def get_recommendations(book_id: UUID, limit: int = 10, db: Session = Depends(get_db)):

    #Get the seed book
    seed_book = db.query(Book).filter(Book.book_id == book_id).first()
    if not seed_book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not seed_book.text_source:
        raise HTTPException(status_code=400, detail="Seed book has no text available")

    #Get all other analysed books that have text
    candidates = db.query(Book).filter(
        Book.book_id != book_id,
        Book.analysed == True,
        Book.text_source != None
    ).limit(500).all()  # cap for performance

    if not candidates:
        raise HTTPException(status_code=404, detail="No candidate books found")

    #Build book dicts for the analyser
    seed = {
        "author": seed_book.author,
        "title": seed_book.title,
        "text": seed_book.text_source
    }
    candidate_list = [
        {"author": b.author, "title": b.title, "text": b.text_source, "book_id": str(b.book_id)}
        for b in candidates
    ]

    #Run Burrows' Delta recommendations
    results = stylometry_analyser.get_recommendations(seed, candidate_list, top_n=limit)

    #Map titles back to full book objects
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