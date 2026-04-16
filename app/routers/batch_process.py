'''
    This file includes the live batch process which is used to loop through 
    100 users in the background and pre computes their recommendations so 
    that when a user opens their profile recommendations should already be populated
'''

import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
 
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import (User, Book, UserBookshelf, StylometricProfile, Recommendation)
from app.feedback_weights import calculate_feedback_adjustment, calculate_stylometric_distance
#calculate_stylometric_distance - weighted euclidean similarity across the stylometric features
#calculate_feedback_adjustment - nudges score up/down based on a user's star ratings

#Uses a python standard logger for logs with tags which can be filtered in Render logs
logger = logging.getLogger(__name__)
 
router = APIRouter(prefix="/recommendations", tags=["recommendations"])

#Config
CACHE_TTL_HOURS = 24 #Any recommendations older than this is stale
MAX_BATCH_SIZE = 100 #This specifies the max users processed in a batch
DEFAULT_BATCH_SIZE = 10 #This is the default amount if its not specified
MAX_RECS_PER_USER = 50 #Shows the recommendations stored per user

#Batch status - stored as plain dict so rests on every Render deploy
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
#Scores every eligible book for single user and stores up to 50 recommendations sorted by descending final score
    #Fetch all user's bookshelf entried
    shelf_entries = db.query(UserBookshelf).filter(
        UserBookshelf.user_id == user_uuid
    ).all()

    #Building a set of book IDs which are already on a users bookshelf 
    shelf_book_ids = {entry.book_id for entry in shelf_entries}
 
    if not shelf_book_ids:
        #If the user has not yet added books to their bookshelf no recommendations can be made
        return []
 
    #This takes all the books a user has rated
    rated_entries = [e for e in shelf_entries if e.rating is not None]

    #Convert the ratings to floats for arithemetic
    for entry in rated_entries:
        try:
            entry.rating = float(entry.rating)
        except (ValueError, TypeError):
            entry.rating = None #If the mask failed change to None

    #Masks which failed cannot be used
    rated_entries = [e for e in rated_entries if e.rating is not None]
    
    #This gets all the books that have been stylometrically analysed that are not a user bookshelf
    candidates = (
        db.query(Book, StylometricProfile)
        .join(StylometricProfile, Book.book_id == StylometricProfile.book_id)
        .filter(
            Book.analysed == True,
            ~Book.book_id.in_(shelf_book_ids), #IDs in this set 
        )
        .limit(6000) #Limit to 6000 to stay within Renders memory
        .all()
    )
 
    if not candidates:
        return []
 
    #This builds rated book profiles for feedback adjustment - pais each rated bookshelf entry with its Stylometric Profile
    user_rated_books = []
    for entry in rated_entries:
        profile = db.query(StylometricProfile).filter(
            StylometricProfile.book_id == entry.book_id
        ).first()
        if profile:
            user_rated_books.append({
                "profile": profile, #StylometricProfile's ORM object
                "rating": float(entry.rating),
            })
 
    #This scores the books
    scored = []
    for book, profile in candidates:
        if user_rated_books:
            #The base score is the average stylometric similarity across all rated books
            base_score = sum(
                calculate_stylometric_distance(profile, item["profile"])
                for item in user_rated_books
            ) / len(user_rated_books)
        else:
            base_score = 0.5
            '''Note: returns [0,1] where 1 is where two books are stylistically identical'''

        #This adjusts the feedback from star ratings defined in feedback_weights.py
        feedback_adj = calculate_feedback_adjustment(profile, user_rated_books)
        
        #Adds up to 0.3 if candidate shares genres with books rated 4 and higher
        genre_boost = calculate_genre_boost(book, user_rated_books, db)

        #Combines all components into ranking score
        final_score = base_score + feedback_adj + genre_boost

        scored.append({
            "book_id": str(book.book_id),
            "title": book.title,
            "author": book.author,
            "cover_url": book.cover_url,
            "summary": book.summary,
            "similarity": round(final_score, 4), #Similarity score
            "delta": round(base_score, 4), #Raw score
            "feedback_adjustment": round(feedback_adj, 4),
            "genre_boost": round(genre_boost, 4),  
        })
 
    #Sort the highest similairy first then truncate to 50
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:MAX_RECS_PER_USER]

def _batch_save_recommendations(user_uuid: UUID, scored: list, db: Session):
#This replaces the users cached recommendations in the recommendation table with new recommendations
    #Delete cache
    db.query(Recommendation).filter(
        Recommendation.user_id == user_uuid
    ).delete()

    #Write each scored book as recommendation row with rank
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

def _is_cache_fresh(user_uuid: UUID, db: Session) -> bool:
#If a user has a fresh cache meaning that reommendations are less than 24 hours then it will avoid recomputing
#Used by run_batch to skip users
    cutoff = datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)
    newest = (
        db.query(Recommendation.generated_at)
        .filter(
            Recommendation.user_id == user_uuid,
            Recommendation.generated_at >= cutoff,
        )
        .first() #Only need to know if fresh rows exists
    )
    return newest is not None #True = fresh cache exists, False = needs recompute

#This batch process will run in the background
def _run_batch(batch_size: int, force_refresh: bool):
#This is a background function triggered by POST /recommendations/batch-process
#Creates own DB session (SessionLocal) as it runs in thread outside FastAPIs request/response lifecycle
    global _batch_status #Mutates module-level dict
 
    _batch_status["running"] = True
    start_time = datetime.utcnow()
    success_count = 0
    error_count = 0
    
    #Create a dedicated session for this background thread
    db: Session = SessionLocal()

    #Pick users who have books stored in their bookshelf (at least one)
    #Join with UserBookshelf to ensure only active users processed 
    try:
        users_with_books = (
            db.query(User)
            .join(UserBookshelf, User.user_id == UserBookshelf.user_id)
            .distinct() #Confirm a user with multiple shelf entries only appear once
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
    
                #Wil score all candidate books
                scored = _score_candidates_for_user(user_uuid, db)
 
                if scored:
                    #Persist the result to recommendations table
                    _batch_save_recommendations(user_uuid, scored, db)
                    logger.debug(
                        f"Batch Saved {len(scored)} recs for {user_uuid}"
                    )
                else:
                    #No book candidates found for user
                    logger.debug(f"Batch No candidates for {user_uuid}")
 
                success_count += 1

            except Exception as e:
                #Catch errors so one bad user doesnt abort whole batch 
                error_count += 1
                logger.error(
                    f"Batch Failed for user {user_uuid}: {e}", exc_info=True
                )
                db.rollback() #Rollback any partial writes

    except Exception as e:
        #Log and fall through to finally
        logger.error(f"Batch Fatal error: {e}", exc_info=True)

    finally:
        #Close database and update status even if crash occurs
        db.close()
 
        duration = (datetime.utcnow() - start_time).total_seconds()
 
        #Update in memory status of dict to reflect completed run
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
#Triggers the batch pre computation as background task - happens asynchronously in _run_batch so HTTP response not blocked
async def trigger_batch_process(
    background_tasks: BackgroundTasks,
    #Users to be processeed
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
    #Prevent a second batch starting while one is running
    if _batch_status["running"]:
        return {
            "message": "A batch job is already running.",
            "status": _batch_status,
        }
    
    #Queues _run_batch as background task - FastAPI runs this in thread after HTTP resonse sent to caller
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
#Returns a genre boost for candidate book - if book has rated 4 and higher, checks how many genres shares with candidate
#Adds boost of 0.1 to book and capped at 0.3 - maximum boost

    #No genres saved for book
    if not candidate_book.genres:
        return 0.0

    #If JSON fails to parse sent back 0
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
            continue #Skip if rated book JSON not right

        shared = candidate_genres & rated_genres 
        if shared:
            #More shared genres is a bigger boost, capped at 0.3
            genre_boost = min(0.1 * len(shared), 0.3)
            boost += genre_boost

    #Cap total boost at 0.3 regardless of how many rated books match
    return min(boost, 0.3)

'''
    Prompt: I am going to create a batch processor for Scriptum which will have these functionalities:
    - A function to score every candidate book for a user and sends back the top 50 books
    - A function to save the cached results
    - Check if the cache is fresh
    - And trigger a batch run on the books as a background task
    Can you please give me a framework or starting point for these tasks?

    Claude response:

    from datetime import datetime, timedelta

    CACHE_TTL_HOURS = 24
    MAX_BATCH_SIZE = 100

    batch_status = {
        "running": False,
        "last_run": None,
        "success_count": 0,
        "error_count": 0,
    }

    def is_cache_fresh(user_id):
        # check if recommendations were generated within 24 hours
        pass

    def score_candidates_for_user(user_id):
        # 1. get user's bookshelf entries
        # 2. get all analysed books not already on shelf
        # 3. for each candidate book:
        #       base_score    = calculate_stylometric_distance(candidate, rated_books)
        #       feedback_adj  = calculate_feedback_adjustment(candidate, rated_books)
        #       genre_boost   = calculate_genre_boost(candidate, rated_books)
        #       final_score   = base_score + feedback_adj + genre_boost
        # 4. sort by final_score descending, return top 50
        pass

    def save_recommendations(user_id, scored_books):
        # 1. delete existing recommendations for user
        # 2. insert new recommendations with rank and score
        # 3. commit to database
        pass

    def run_batch(batch_size, force_refresh):
        batch_status["running"] = True

        users = get_users_with_bookshelf_entries(limit=batch_size)

        for user in users:
            try:
                if not force_refresh and is_cache_fresh(user.id):
                    continue  # skip — recommendations still valid

                scored = score_candidates_for_user(user.id)

                if scored:
                    save_recommendations(user.id, scored)

                batch_status["success_count"] += 1

            except Exception as e:
                batch_status["error_count"] += 1
                rollback()

        batch_status["running"] = False
        batch_status["last_run"] = datetime.utcnow().isoformat()
'''