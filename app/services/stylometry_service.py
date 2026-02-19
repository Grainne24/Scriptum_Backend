'''
    This file uses stylometry to analyse the writing style of book texts
    using the faststylometry library's Corpus-based Burrows' Delta approach.
'''

from faststylometry import Corpus
from faststylometry.en import tokenise_remove_pronouns_en
from faststylometry.burrows_delta import calculate_burrows_delta
from typing import Dict, List
import re
import math


class StylometryAnalyser:

    def build_corpus(self, books: List[Dict]) -> Corpus:
        #Builds a faststylometry Corpus from a list of books
        corpus = Corpus()
        for book in books:
            corpus.add_book(book['author'], book['title'], book['text'])
        corpus.tokenise(tokenise_remove_pronouns_en)
        return corpus

    def get_recommendations(self, seed_book: Dict, candidate_books: List[Dict], top_n: int = 10) -> List[Dict]:
        #Given a seed book, recommends the most stylistically similar books
        #Build the train corpus from all candidate books
        train_corpus = self.build_corpus(candidate_books)

        # uild the test corpus from just the seed book
        test_corpus = self.build_corpus([seed_book])

        #Calculate Burrows' Delta
        delta_df = calculate_burrows_delta(train_corpus, test_corpus)

        #delta_df has candidate books as rows and the seed book as column
        seed_col = delta_df.columns[0]  #The seed book column

        results = []
        for candidate_title, delta_score in delta_df[seed_col].items():
            #Skip if it's the same book as the seed
            if candidate_title == seed_book['title']:
                continue

            #Convert delta to a 0-1 similarity score
            similarity = round(1 / (1 + delta_score), 4)

            results.append({
                "title": candidate_title,
                "delta": round(float(delta_score), 4),
                "similarity": similarity
            })

        #Sort by delta ascending
        results.sort(key=lambda x: x['delta'])

        return results[:top_n]

    def calculate_delta_between_two(self, book1: Dict, book2: Dict) -> Dict:
        #Calculates Burrows' Delta between exactly two books.
        #Returns delta score and similarity score.
        train_corpus = self.build_corpus([book1])
        test_corpus = self.build_corpus([book2])

        delta_df = calculate_burrows_delta(train_corpus, test_corpus)
        delta_score = float(delta_df.iloc[0, 0])
        similarity = round(1 / (1 + delta_score), 4)

        return {
            "delta": round(delta_score, 4),
            "similarity": similarity
        }

    def analyse_text(self, text: str) -> Dict[str, float]:
       
        #Calculates supplementary stylometric display metrics. These are NOT used for recommendations (Burrows' Delta handles that) but are shown on the book profile screen in the app.
        if not text or len(text.strip()) == 0:
            raise ValueError("Text cannot be empty")

        words = re.findall(r'\b[a-zA-Z]+\b', text)
        sentences = self._split_sentences(text)

        total_words = len(words)
        total_sentences = len(sentences)
        unique_words = len(set(word.lower() for word in words))

        avg_sentence_length = total_words / total_sentences if total_sentences > 0 else 0
        avg_word_length = sum(len(word) for word in words) / total_words if total_words > 0 else 0
        lexical_diversity = unique_words / total_words if total_words > 0 else 0

        #Pacing score
        if total_sentences > 1:
            sentence_lengths = [len(s.split()) for s in sentences]
            avg_len = sum(sentence_lengths) / len(sentence_lengths)
            variance = sum((x - avg_len) ** 2 for x in sentence_lengths) / len(sentence_lengths)
            std_dev = math.sqrt(variance)
            cv = (std_dev / avg_len * 100) if avg_len > 0 else 0
            pacing_score = min(100, cv)
        else:
            pacing_score = 50.0

        #Tone score
        exclamation_count = text.count('!')
        question_count = text.count('?')
        emotional_punctuation = exclamation_count + question_count
        tone_score = min(100, (emotional_punctuation / total_sentences) * 50) if total_sentences > 0 else 0

        vocabulary_richness = lexical_diversity * 100

        #Dialogue percentage
        dialogue_pattern = r'[""][^""]+[""]|"[^"]+"'
        dialogue_matches = re.findall(dialogue_pattern, text)
        dialogue_words = sum(len(match.split()) for match in dialogue_matches)
        dialogue_percentage = (dialogue_words / total_words * 100) if total_words > 0 else 0

        #Punctuation density
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

    def _split_sentences(self, text: str) -> list:
        try:
            from nltk.tokenize import sent_tokenize
            sentences = sent_tokenize(text)
        except ImportError:
            text = re.sub(r'\bMrs\.', 'MrsXXX', text)
            text = re.sub(r'\bMr\.', 'MrXXX', text)
            text = re.sub(r'\bDr\.', 'DrXXX', text)
            text = re.sub(r'\bMs\.', 'MsXXX', text)
            text = re.sub(r'\bSt\.', 'StXXX', text)
            text = re.sub(r'\bProf\.', 'ProfXXX', text)
            text = re.sub(r'\bvs\.', 'vsXXX', text)

            sentences = re.split(r'[.!?]+', text)

            sentences = [
                s.replace('MrsXXX', 'Mrs.')
                 .replace('MrXXX', 'Mr.')
                 .replace('DrXXX', 'Dr.')
                 .replace('MsXXX', 'Ms.')
                 .replace('StXXX', 'St.')
                 .replace('ProfXXX', 'Prof.')
                 .replace('vsXXX', 'vs.')
                for s in sentences
            ]

        return [s.strip() for s in sentences if s.strip() and len(s.split()) >= 3]


#Singleton instance
stylometry_analyser = StylometryAnalyser()