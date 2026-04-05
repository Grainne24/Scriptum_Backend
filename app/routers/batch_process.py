'''
    This file includes the live batch process which is used to loop through 100 users in the background and pre computes their recommendations so that when a user opens their profile recommendations should already be populated
'''

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
 
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import (User, Book, UserBookshelf, StylometricProfile, Recommendation)
from app.feedback_weights import calculate_feedback_adjustment

logger = logging.getLogger(__name__)
 
router = APIRouter(prefix="/recommendations", tags=["recommendations"])

#Config
CACHE_TTL_HOURS = 24 #Any recommendations older than this is stale
MAX_BATCH_SIZE = 100 #This specifies the max users processed in a batch
DEFAULT_BATCH_SIZE = 10 #This is the default amount if its not specified
MAX_RECS_PER_USER = 50 #Shows the recommendations stored per user

#Batch status 
_batch_status = {
    "running": False,
    "last_run": None,
    "last_run_user_count": 0,
    "last_run_success_count": 0,
    "last_run_error_count": 0,
    "last_run_duration_seconds": 0,
}

#This portion mimics recommendations.py 
def _score_candidates_for_user(user_uuid: UUID, db: Session) -> list:

    shelf_entries = db.query(UserBookshelf).filter(
        UserBookshelf.user_id == user_uuid
    ).all()

    shelf_book_ids = {entry.book_id for entry in shelf_entries}
 
    if not shelf_book_ids:
        #If the user has not yet added books to their bookshelf no recommendations can be made
        return []
 
    #This takes all the books a user has taken
    rated_entries = [e for e in shelf_entries if e.rating is not None]

    #Convert the ratings to floats
    for entry in rated_entries:
        try:
            entry.rating = float(entry.rating)
        except (ValueError, TypeError):
            entry.rating = None

    rated_entries = [e for e in rated_entries if e.rating is not None]
    
    #This gets all the books that have been stylometrically analysed
    candidates = (
        db.query(Book, StylometricProfile)
        .join(StylometricProfile, Book.book_id == StylometricProfile.book_id)
        .filter(
            Book.analysed == True,
            ~Book.book_id.in_(shelf_book_ids),
        )
        .limit(6000)
        .all()
    )
 
    if not candidates:
        return []
 
    #This builds rated book profiles for feedback adjustment
    user_rated_books = []
    for entry in rated_entries:
        profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == entry.book_id
        ).first()
        if profile:
            user_rated_books.append({
                "profile": profile,
                "rating": float(entry.rating),
            })
 
    #This scores the books
    scored = []
    for book, profile in candidates:
        base_score = 0.5
 
        #This adjusts the feedback from star ratings
        feedback_adj = calculate_feedback_adjustment(profile, user_rated_books)
        genre_boost = calculate_genre_boost(book, user_rated_books, db)

        final_score = (base_score * 2) + feedback_adj + genre_boost

        scored.append({
            "book_id": str(book.book_id),
            "title": book.title,
            "author": book.author,
            "cover_url": book.cover_url,
            "summary": book.summary,
            "similarity": round(final_score, 4),
            "delta": round(base_score, 4),
            "feedback_adjustment": round(feedback_adj, 4),
            "genre_boost": round(genre_boost, 4),  
        })
 
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:MAX_RECS_PER_USER]

def _batch_save_recommendations(user_uuid: UUID, scored: list, db: Session):
    db.query(Recommendation).filter(
        Recommendation.user_id == user_uuid
    ).delete()

    for rank, item in enumerate(scored, start=1):
        rec = Recommendation(
            recommendation_id=uuid.uuid4(),
            user_id=user_uuid,
            book_id=UUID(item["book_id"]),
            similarity_score=item["similarity"],
            rank=rank,
            generated_at=datetime.utcnow(),
        )
        db.add(rec)
 
    db.commit()

#This returns up to date recommendations to a user
def _is_cache_fresh(user_uuid: UUID, db: Session) -> bool:
    cutoff = datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)
    newest = (
        db.query(Recommendation.generated_at)
        .filter(
            Recommendation.user_id == user_uuid,
            Recommendation.generated_at >= cutoff,
        )
        .first()
    )
    return newest is not None

#This batch process will run in the background
def _run_batch(batch_size: int, force_refresh: bool):
    global _batch_status
 
    _batch_status["running"] = True
    start_time = datetime.utcnow()
    success_count = 0
    error_count = 0
 
    db: Session = SessionLocal()

    #Pick users who have books stored in their bookshelf (at least one)
    try:
        users_with_books = (
            db.query(User)
            .join(UserBookshelf, User.user_id == UserBookshelf.user_id)
            .distinct()
            .limit(batch_size)
            .all()
        )
    
        logger.info(
            f"Batch Starting — {len(users_with_books)} users, force_refresh={force_refresh}"
        )
 
        for user in users_with_books:
            user_uuid = user.user_id

            try:
                #If the cache is fresh then it will skip
                if not force_refresh and _is_cache_fresh(user_uuid, db):
                    logger.debug(f"Batch Skipping {user_uuid} as cache fresh")
                    success_count += 1
                    continue

                logger.debug(f"Batch Processing {user_uuid}")
 
                scored = _score_candidates_for_user(user_uuid, db)
 
                if scored:
                    _batch_save_recommendations(user_uuid, scored, db)
                    logger.debug(
                        f"Batch Saved {len(scored)} recs for {user_uuid}"
                    )
                else:
                    logger.debug(f"Batch No candidates for {user_uuid}")
 
                success_count += 1

            except Exception as e:
                error_count += 1
                logger.error(
                    f"Batch Failed for user {user_uuid}: {e}", exc_info=True
                )
                db.rollback()

    except Exception as e:
        logger.error(f"Batch Fatal error: {e}", exc_info=True)

    finally:
        db.close()
 
        duration = (datetime.utcnow() - start_time).total_seconds()
 
        _batch_status.update({
            "running": False,
            "last_run": datetime.utcnow().isoformat(),
            "last_run_user_count": len(users_with_books) if 'users_with_books' in dir() else 0,
            "last_run_success_count": success_count,
            "last_run_error_count": error_count,
            "last_run_duration_seconds": round(duration, 2),
        })
 
        logger.info(
            f"Batch Done {success_count}, {error_count} errors, {duration:.1f}s"
        )

#Endpoints
@router.post("/batch-process")
async def trigger_batch_process(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(
        default=DEFAULT_BATCH_SIZE,
        ge=1,
        le=MAX_BATCH_SIZE,
        description="Number of users to process (1-100)",
    ),
    force_refresh: bool = Query(
        default=False,
        description="Recomputing",
    ),
    db: Session = Depends(get_db),
):
    if _batch_status["running"]:
        return {
            "message": "A batch job is already running.",
            "status": _batch_status,
        }
    
    background_tasks.add_task(_run_batch, batch_size, force_refresh)
 
    return {
        "message": f"Batch started for up to {batch_size} users.",
        "force_refresh": force_refresh,
        "check_status_at": "/recommendations/batch-status",
    }

#This checks if the batch process is working or not
@router.get("/batch-status")
async def get_batch_status():
    return _batch_status

def calculate_genre_boost(candidate_book: Book, user_rated_books: list, db: Session) -> float:

    if not candidate_book.genres:
        return 0.0

    try:
        candidate_genres = set(json.loads(candidate_book.genres))
    except Exception:
        return 0.0

    if not candidate_genres:
        return 0.0

    boost = 0.0

    for item in user_rated_books:
        rating = float(item["rating"])
        if rating < 4.0:
            continue  #Only boosts the rating based on books the user actually liked

        #Gets the rated book to check all its genres
        rated_book = db.query(Book).filter(
            Book.book_id == item["profile"].book_id
        ).first()

        if not rated_book or not rated_book.genres:
            continue

        try:
            rated_genres = set(json.loads(rated_book.genres))
        except Exception:
            continue

        shared = candidate_genres & rated_genres 
        if shared:
            #More shared genres is a bigger boost, capped at 0.3
            genre_boost = min(0.1 * len(shared), 0.3)
            boost += genre_boost

    #ap total boost at 0.3 regardless of how many rated books match
    return min(boost, 0.3)