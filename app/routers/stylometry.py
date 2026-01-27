'''
    This file is the endpoints to trigger analysis and retrieve results
'''

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models import Book, StylometricProfile
from app.services.stylometry_service import stylometry_analyzer
from app.services.gutendex_service import gutendex_service

router = APIRouter(prefix="/stylometry", tags=["stylometry"])

#This fetches the book text from gutenberg and analyses it
@router.post("/analyze-from-gutenberg/{book_id}", response_model=dict)
async def analyze_book_from_gutenberg(
    book_id: UUID,
    db: Session = Depends(get_db)
):
    #Get books from database
    book = db.query(Book).filter(Book.book_id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    #Check if it has already been analysed
    existing_profile = db.query(StylometricProfile).filter(
        StylometricProfile.book_id == book_id
    ).first()
    
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Book has already been analysed"
        )
    
    #Extracts the Gutenberg ID from text_source
    if not book.text_source or "gutenberg_" not in book.text_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Book is not from Project Gutenberg. Import from Gutenberg first."
        )
    
    try:
        gutenberg_id = int(book.text_file_path.replace("gutenberg_", ""))
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Gutenberg ID format"
        )
    
    #Fetches the book text
    try:
        text = await gutendex_service.get_book_text(gutenberg_id)
        
        if not text:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not download text for Gutenberg ID {gutenberg_id}"
            )
        
        #Analyses the text
        analysis_results = stylometry_analyzer.analyze_text(text)
        
        #Creates a stylometric profile
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
        
        #This adds any optional fields if they exist
        if hasattr(StylometricProfile, 'punctuation_density'):
            profile.punctuation_density = analysis_results.get("punctuation_density")
        if hasattr(StylometricProfile, 'dialogue_percentage'):
            profile.dialogue_percentage = analysis_results.get("dialogue_percentage")
        
        db.add(profile)
        
        #Updatse book as analysed
        book.analysed = True
        
        db.commit()
        db.refresh(profile)
        
        return {
            "message": "Book analysed successfully",
            "book_id": str(book_id),
            "book_title": book.title,
            "gutenberg_id": gutenberg_id,
            "analysis": analysis_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )
#This analyses a book with its provided text
@router.post("/analyze/{book_id}", response_model=dict)
def analyze_book_with_text(
    book_id: UUID,
    text: str,
    db: Session = Depends(get_db)
):
    #Checks if book exists
    book = db.query(Book).filter(Book.book_id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    #Checks if it already has been analysed
    existing_profile = db.query(StylometricProfile).filter(
        StylometricProfile.book_id == book_id
    ).first()
    
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Book has already been analysed"
        )
    
    try:
        #Analysee the text
        analysis_results = stylometry_analyzer.analyze_text(text)
        
        #Creates a stylometric profile
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
        
        db.add(profile)
        book.analysed = True
        
        db.commit()
        db.refresh(profile)
        
        return {
            "message": "Book analysed successfully",
            "book_id": str(book_id),
            "analysis": analysis_results
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )

@router.get("/profile/{book_id}")
def get_stylometric_profile(book_id: UUID, db: Session = Depends(get_db)):
    
    profile = db.query(StylometricProfile).filter(
        StylometricProfile.book_id == book_id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stylometric profile not found. Book may not be analysed yet."
        )
    
    return {
        "book_id": str(profile.book_id),
        "pacing_score": float(profile.pacing_score) if profile.pacing_score else None,
        "tone_score": float(profile.tone_score) if profile.tone_score else None,
        "vocabulary_richness": float(profile.vocabulary_richness) if profile.vocabulary_richness else None,
        "avg_sentence_length": float(profile.avg_sentence_length) if profile.avg_sentence_length else None,
        "avg_word_length": float(profile.avg_word_length) if profile.avg_word_length else None,
        "lexical_diversity": float(profile.lexical_diversity) if profile.lexical_diversity else None,
        "total_words": profile.total_words,
        "total_sentences": profile.total_sentences,
        "unique_words": profile.unique_words,
        "analysed_at": profile.analysed_at
    }