'''
    This file uses stylometry to analyse the writing style of book texts
'''

from faststylometry import calculate_burrows_delta
import os
from typing import Dict, Optional
import re
import math


class StylometryAnalyser:
    
    def analyse_text(self, text: str) -> Dict[str, float]:
        if not text or len(text.strip()) == 0:
            raise ValueError("Text cannot be empty")
        
        #Splits text into words and sentences
        words = text.split()
        sentences = self._split_sentences(text)
        
        #Calculates the basic statistics
        total_words = len(words)
        total_sentences = len(sentences)
        unique_words = len(set(word.lower() for word in words))
        
        #Calculate the rest of the metrics
        avg_sentence_length = total_words / total_sentences if total_sentences > 0 else 0
        avg_word_length = sum(len(word) for word in words) / total_words if total_words > 0 else 0
        lexical_diversity = unique_words / total_words if total_words > 0 else 0
        
        #Calculate the pacing score (based on sentence length variation)
        if total_sentences > 1:
            sentence_lengths = [len(s.split()) for s in sentences]
            avg_len = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((x - avg_len) ** 2 for x in sentence_lengths) / len(sentence_lengths)
            std_dev = math.sqrt(variance) #normalisation 
            cv = (std_dev / avg_len * 100) if avg_len > 0 else 0
            pacing_score = min(100, cv)
        else:
            pacing_score = 50.0
        
        #Calculate the tone score (based on emotional punctuation)
        exclamation_count = text.count('!')
        question_count = text.count('?')
        emotional_punctuation = exclamation_count + question_count
        tone_score = min(100, (emotional_punctuation / total_sentences) * 50) if total_sentences > 0 else 0
        
        #Calculates the vocabulary richness (lexical diversity scaled to 0-100)
        vocabulary_richness = lexical_diversity * 100
        
        #Calculates the dialogue percentage
        dialogue_pattern = r'[""][^""]+[""]|"[^"]+"'
        dialogue_matches = re.findall(dialogue_pattern, text)
        dialogue_words = sum(len(match.split()) for match in dialogue_matches)
        dialogue_percentage = (dialogue_words / total_words * 100) if total_words > 0 else 0
        
        #Calculates the punctuation density
        punctuation_density = sum(1 for char in text if char in ',.!?;:') / total_words if total_words > 0 else 0
        
        return {
            "pacing_score": round(pacing_score, 2),
            "tone_score": round(tone_score, 2),
            "vocabulary_richness": round(vocabulary_richness, 2),
            "avg_sentence_length": round(avg_sentence_length, 2),
            "avg_word_length": round(avg_word_length, 2),
            "lexical_diversity": round(lexical_diversity, 4),
            "punctuation_density": round(punctuation_density, 4),
            "dialogue_percentage": round(dialogue_percentage, 2),
            "total_words": total_words,
            "total_sentences": total_sentences,
            "unique_words": unique_words
        }
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        try:
            #Calculate Burrows' Delta using faststylometry
            delta = calculate_burrows_delta(text1, text2)
            
            #Convert to similarity score (0-1 range, where 1 = most similar)
            similarity = 1 / (1 + delta)
            
            return similarity
            
        except Exception as e:
            print(f"Error calculating Burrows' Delta: {e}")
            return 0.0
    
    def _split_sentences(self, text: str) -> list:
        try:
            #Try using NLTK if available (best for complex texts)
            from nltk.tokenize import sent_tokenize
            sentences = sent_tokenize(text)
        except ImportError:
            #This is a fallback incase nltk doesn't work
            text = re.sub(r'\bMrs\.', 'MrsXXX', text)
            text = re.sub(r'\bMr\.', 'MrXXX', text)
            text = re.sub(r'\bDr\.', 'DrXXX', text)
            text = re.sub(r'\bMs\.', 'MsXXX', text)
            text = re.sub(r'\bSt\.', 'StXXX', text)
            
            #Split on sentence-ending punctuation followed by space and capital letter
            sentences = re.split(r'[.!?]+\s+(?=[A-Z])', text)
            
            #Restore abbreviations
            sentences = [
                s.replace('MrsXXX', 'Mrs.')
                 .replace('MrXXX', 'Mr.')
                 .replace('DrXXX', 'Dr.')
                 .replace('MsXXX', 'Ms.')
                 .replace('StXXX', 'St.')
                for s in sentences
            ]
        
        #Filter out very short sentences (likely artifacts)
        return [s.strip() for s in sentences if s.strip() and len(s.split()) >= 3]
    
    def calculate_normalized_similarity(self, profile1, profile2, db) -> Dict[str, float]:
        from sqlalchemy import func
        from app.models import StylometricProfile

        #Get min/max values across all books for normalisation
        stats = db.query(
            func.min(StylometricProfile.pacing_score).label('min_pacing'),
            func.max(StylometricProfile.pacing_score).label('max_pacing'),
            func.min(StylometricProfile.tone_score).label('min_tone'),
            func.max(StylometricProfile.tone_score).label('max_tone'),
            func.min(StylometricProfile.vocabulary_richness).label('min_vocab'),
            func.max(StylometricProfile.vocabulary_richness).label('max_vocab'),
            func.min(StylometricProfile.avg_sentence_length).label('min_sent'),
            func.max(StylometricProfile.avg_sentence_length).label('max_sent')
        ).first()
        
        #Normalise the pacing
        norm_pacing1 = (profile1.pacing_score - stats.min_pacing) / (stats.max_pacing - stats.min_pacing) if stats.max_pacing != stats.min_pacing else 0
        norm_pacing2 = (profile2.pacing_score - stats.min_pacing) / (stats.max_pacing - stats.min_pacing) if stats.max_pacing != stats.min_pacing else 0
        pacing_sim = 1 - abs(norm_pacing1 - norm_pacing2)
        
        #Normalise the tone
        norm_tone1 = (profile1.tone_score - stats.min_tone) / (stats.max_tone - stats.min_tone) if stats.max_tone != stats.min_tone else 0
        norm_tone2 = (profile2.tone_score - stats.min_tone) / (stats.max_tone - stats.min_tone) if stats.max_tone != stats.min_tone else 0
        tone_sim = 1 - abs(norm_tone1 - norm_tone2)
        
        #Normalise the vocabulary
        norm_vocab1 = (profile1.vocabulary_richness - stats.min_vocab) / (stats.max_vocab - stats.min_vocab) if stats.max_vocab != stats.min_vocab else 0
        norm_vocab2 = (profile2.vocabulary_richness - stats.min_vocab) / (stats.max_vocab - stats.min_vocab) if stats.max_vocab != stats.min_vocab else 0
        vocab_sim = 1 - abs(norm_vocab1 - norm_vocab2)
        
        #Normalise the sentence length
        norm_sent1 = (profile1.avg_sentence_length - stats.min_sent) / (stats.max_sent - stats.min_sent) if stats.max_sent != stats.min_sent else 0
        norm_sent2 = (profile2.avg_sentence_length - stats.min_sent) / (stats.max_sent - stats.min_sent) if stats.max_sent != stats.min_sent else 0
        sent_sim = 1 - abs(norm_sent1 - norm_sent2)
        
        return {
            "pacing_similarity": pacing_sim,
            "tone_similarity": tone_sim,
            "vocabulary_similarity": vocab_sim,
            "sentence_length_similarity": sent_sim
        }

#Creates singleton instance
stylometry_analyser = StylometryAnalyser()