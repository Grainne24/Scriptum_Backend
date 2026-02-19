from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Book, UserBookshelf
from app.services.stylometry_service import stylometry_analyser
from app.services.gutendex_service import gutendex_service
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

        #Get shelf books that have a gutenberg_id
        shelf_books = db.query(Book).filter(
            Book.book_id.in_(shelf_book_ids),
            Book.gutenberg_id != None,
            Book.analysed == True
        ).all()

        if not shelf_books:
            raise HTTPException(status_code=400, detail="No analysed Gutenberg books found on shelf")

        #Get candidate books not on the shelf
        candidates = db.query(Book).filter(
            Book.book_id.notin_(shelf_book_ids),
            Book.gutenberg_id != None,
            Book.analysed == True
        ).limit(50).all()  

        if not candidates:
            raise HTTPException(status_code=404, detail="No candidate books found")

        #Fetch shelf book texts from Gutenberg
        print("Fetching shelf book texts...")
        shelf_texts = []
        for book in shelf_books:
            try:
                text = await gutendex_service.get_book_text(book.gutenberg_id)
                if text:
                    shelf_texts.append(text[:100000]) 
                    print(f"  Got text for: {book.title[:50]}")
            except Exception as e:
                print(f"  Failed for {book.title}: {e}")
                continue

        if not shelf_texts:
            raise HTTPException(status_code=400, detail="Could not fetch text for any shelf books")

        #Fetch candidate book texts from Gutenberg
        print("Fetching candidate book texts...")
        candidate_list = []
        for book in candidates:
            try:
                text = await gutendex_service.get_book_text(book.gutenberg_id)
                if text:
                    candidate_list.append({
                        "author": book.author,
                        "title": book.title,
                        "text": text[:30000],
                        "book_id": str(book.book_id)
                    })
                    print(f"  Got text for: {book.title[:50]}")
            except Exception as e:
                print(f"  Failed for {book.title}: {e}")
                continue

        if not candidate_list:
            raise HTTPException(status_code=404, detail="Could not fetch text for any candidate books")

        #Build seed from combined shelf texts
        combined_user_text = " ".join(shelf_texts)
        seed = {
            "author": "User Profile",
            "title": "User Bookshelf",
            "text": combined_user_text
        }

        #Run Burrows' Delta
        results = stylometry_analyser.get_recommendations(seed, candidate_list, top_n=limit)

        #Map results back to book objects
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

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"RECOMMENDATION ERROR: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")
    
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
    ).limit(500).all()  

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

    print(f"Delta results: {results}")
    print(f"title_to_book keys: {list(title_to_book.keys())[:5]}")
            
    results = stylometry_analyser.get_recommendations(seed, candidate_list, top_n=limit)

    print(f"Raw delta results: {results}")
    print(f"Number of results: {len(results)}")
    print(f"Candidate titles in map: {list(title_to_book.keys())}")


    return response
