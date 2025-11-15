'''
    This file uses stylometry to analyse the writing style of book texts
'''

from faststylometry import load_corpus_from_folder, calculate_burrows_delta
import os
from typing import Dict, Optional
import re

class StylometryAnalyzer:
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        if not text or len(text.strip()) == 0:
            raise ValueError("Text cannot be empty")
        
        #Splits text into words and sentences
        words = text.split()
        sentences = self._split_sentences(text)
        
        #Calculates the basic statistics
        total_words = len(words)
        total_sentences = len(sentences)
        unique_words = len(set(word.lower() for word in words))
        
        #Calculate the metrics
        avg_sentence_length = total_words / total_sentences if total_sentences > 0 else 0
        avg_word_length = sum(len(word) for word in words) / total_words if total_words > 0 else 0
        lexical_diversity = unique_words / total_words if total_words > 0 else 0
        
        #Calculate the pacing score (based on sentence length variation)
        if total_sentences > 1:
            sentence_lengths = [len(s.split()) for s in sentences]
            avg_len = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((x - avg_len) ** 2 for x in sentence_lengths) / len(sentence_lengths)
            pacing_score = min(100, variance)  #This is normalised from 0-100
        else:
            pacing_score = 50.0
        
        #Calculate the tone score (placeholder - can be enhanced with sentiment analysis)
        punctuation_count = sum(1 for char in text if char in '!?.')
        tone_score = min(100, (punctuation_count / total_sentences) * 10) if total_sentences > 0 else 50.0
        
        #Calculates the vocabulary richness (lexical diversity scaled to 0-100)
        vocabulary_richness = lexical_diversity * 100
        
        #Calculates the dialogue percentage (this is a rough estimate)
        dialogue_chars = text.count('"') + text.count("'")
        dialogue_percentage = min(100, (dialogue_chars / len(text)) * 200) if len(text) > 0 else 0
        
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
            "unique_words": unique_words,
            "start": words

        }
    
    def _split_sentences(self, text: str) -> list:
        """Split text into sentences"""
        #Simple sentence splitting
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]

#Creates singleton instance
stylometry_analyzer = StylometryAnalyzer()