'''
    This file uses stylometry to analyse the writing style of book texts
    using the faststylometry library's Corpus-based Burrows' Delta approach.
'''

from faststylometry import Corpus
from faststylometry.en import tokenise_remove_pronouns_en
from faststylometry.burrows_delta import calculate_burrows_delta
from typing import Dict, List
import re
import nltk


class StylometryAnalyser:
#This class wraps all stylomeric functionality into one object

    def build_corpus(self, books: List[Dict]) -> Corpus:
        #Builds a faststylometry Corpus from a list of books
        #Called by get_recommendations() and calculcate_delta_between_two()
        corpus = Corpus()
        for book in books:
            corpus.add_book(book['author'], book['title'], book['text'])
            #Each book added to corpus
        corpus.tokenise(tokenise_remove_pronouns_en)
        #Tokenises each book in corpus using pronoun-removing english tokens
        return corpus

    def get_recommendations(self, seed_book: Dict, candidate_books: List[Dict], top_n: int = 10) -> List[Dict]:
    #Finds top_n most stylistically similiar books to seed - uses burrows delta for book to book endpoints
    #Used for cross validation testing against custom algorithm
        print(f"get_recommendations called with {len(candidate_books)} candidates")
        train_corpus = self.build_corpus(candidate_books) #Candidate book becomes training corpus
        test_corpus = self.build_corpus([seed_book]) #Seed book becomes test corpus
        delta_df = calculate_burrows_delta(train_corpus, test_corpus) #Conducts Burrows Delta between every candidate and seed book
        seed_col = delta_df.columns[0]

        print(f"Delta columns: {delta_df.columns.tolist()}")
        print(f"Delta index: {delta_df.index.tolist()}")

        #Build author -> title lookup from candidate_books as indexes by author name ot title
        author_to_title = {book['author']: book['title'] for book in candidate_books} 

        results = []
        for candidate_author, delta_score in delta_df[seed_col].items():
            #Look up title from author
            candidate_title = author_to_title.get(candidate_author)
            if not candidate_title:
                print(f"No title found for author: {candidate_author}")
                continue #Skip if title not found

            if candidate_title == seed_book['title']:
                continue #Skip seed book

            similarity = round(1 / (1 + delta_score), 4)
            #Convert delta distance to similairty score

            results.append({
                "title": candidate_title,
                "delta": round(float(delta_score), 4),
                "similarity": similarity
            })

        #Sort by delta ascending - lowest delta = most similar style 
        results.sort(key=lambda x: x['delta'])
        print(f"Returning {len(results)} results")
        return results[:top_n]
    
    def calculate_delta_between_two(self, book1: Dict, book2: Dict) -> Dict:
    #Calculates Burrows' Delta between exactly two books.
    #Returns delta score and similarity score.
        train_corpus = self.build_corpus([book1, book2])
        test_corpus = self.build_corpus([book2])

        delta_df = calculate_burrows_delta(train_corpus, test_corpus)
        delta_score = float(delta_df.iloc[0, 0])
        similarity = round(1 / (1 + delta_score), 4)

        return {
            "delta": round(delta_score, 4),
            "similarity": similarity
        }

    def analyse_text(self, text: str) -> Dict[str, float]:
    #Custom-built stylometric analyser 
        if not text or len(text.strip()) == 0:
            raise ValueError("Text cannot be empty")

        words = re.findall(r'\b[a-zA-Z]+\b', text) #Strips punctuation, numbers and special characters
        sentences = self._split_sentences(text) #Splits sentences

        total_words = len(words)
        total_sentences = len(sentences)
        unique_words = len(set(word.lower() for word in words)) #Counts unique words without duplicates

        #Average words per sentence which guards against division by 0
        avg_sentence_length = total_words / total_sentences if total_sentences > 0 else 0
        #Average characters per word - longer words = more complex
        avg_word_length = sum(len(word) for word in words) / total_words if total_words > 0 else 0
        #unique words compared to total words - higher = more varied
        lexical_diversity = unique_words / total_words if total_words > 0 else 0

        #Pacing score
        action_verbs = {
            'ran', 'rushed', 'jumped', 'grabbed', 'shouted', 'screamed',
            'fled', 'attacked', 'burst', 'crashed', 'dashed', 'seized',
            'struck', 'fell', 'shot', 'threw', 'leapt', 'sprinted',
            'escaped', 'exploded', 'charged', 'spun', 'ducked', 'swung'
        }
        words_lower = [w.lower() for w in words] #Lowercase
        #Proportion of words which are action verbs
        action_verb_density = sum(1 for w in words_lower if w in action_verbs) / total_words if total_words > 0 else 0

        #Sentence length component
        sentence_length_pacing = max(0, 100 - (avg_sentence_length * 2.5))

        #Combine the two so 70% is sentence length and 30% action verb density
        #Note: action word is tiny thats why its times 3000
        pacing_score = min(100, (sentence_length_pacing * 0.7) + (action_verb_density * 3000 * 0.3))

        #Tone score
        dark_words = {
            'death', 'dead', 'die', 'died', 'kill', 'killed', 'murder', 'blood',
            'darkness', 'shadow', 'despair', 'grief', 'sorrow', 'fear', 'horror',
            'dread', 'terror', 'agony', 'suffering', 'pain', 'misery', 'doom',
            'wretched', 'evil', 'curse', 'hate', 'hatred', 'rage', 'fury'
        }
        positive_words = {
            'joy', 'happy', 'happiness', 'love', 'laugh', 'laughter', 'smile',
            'hope', 'light', 'bright', 'beautiful', 'wonderful', 'delight',
            'pleasure', 'peace', 'gentle', 'kind', 'warm', 'sweet', 'cheer',
            'merry', 'glad', 'blessed', 'radiant', 'celebrate', 'dream'
        }
        #Proportion of matching words to this set
        dark_density   = sum(1 for w in words_lower if w in dark_words) / total_words if total_words > 0 else 0
        positive_density = sum(1 for w in words_lower if w in positive_words) / total_words if total_words > 0 else 0

        #Tone score
        #Starts at 50 which is neutral, positive words push it above 50, dark words pull it below.
        tone_score = 50 + ((positive_density - dark_density) * 1000)
        tone_score = max(0, min(100, tone_score)) #clamp between [0,100]

        #Vocabulary richness
        #Sliding window method
        window_size = 1000
        if total_words >= window_size:
            window_scores = []
            for i in range(0, total_words - window_size, window_size // 2):
                #50% overlap which smooths score so a single unsual pattern doesnt skew result
                window = words_lower[i:i + window_size]
                #TTR across all windows rather than globally
                window_scores.append(len(set(window)) / window_size)
            vocab_richness_raw = sum(window_scores) / len(window_scores) if window_scores else lexical_diversity
        else:
            vocab_richness_raw = lexical_diversity #If text to short for windowing it falls back to global TTR

        vocabulary_richness = round(vocab_richness_raw * 100, 2)

        #Dialogue percentage
        #This portion was aided by Claude
        dialogue_pattern = r'[""][^""]+[""]|"[^"]+"'
        #This was the fix for the original zero-dialogue bug on Through the Looking Glass
        dialogue_matches = re.findall(dialogue_pattern, text)
        dialogue_words = sum(len(match.split()) for match in dialogue_matches)
        #Count total words inside quotes
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
        } #11 values returned as Dict and saved to StylometricProfile table - used to populate radar chart

    def _split_sentences(self, text: str) -> list: 
        #First tried NLTK then falls back to manual regex apprach if NLTK available on server
        try:
            from nltk.tokenize import sent_tokenize
            try:
                sentences = sent_tokenize(text) #Handles abbreviations, etc
            except LookupError:
                nltk.download('punkt_tab', quiet=True)
                sentences = sent_tokenize(text)
        except ImportError:
            #E.g. if Mr. Doe ran. should not be two sentences
            text = re.sub(r'\bMrs\.', 'MrsXXX', text)
            text = re.sub(r'\bMr\.', 'MrXXX', text)
            text = re.sub(r'\bDr\.', 'DrXXX', text)
            text = re.sub(r'\bMs\.', 'MsXXX', text)
            text = re.sub(r'\bSt\.', 'StXXX', text)
            text = re.sub(r'\bProf\.', 'ProfXXX', text)
            text = re.sub(r'\bvs\.', 'vsXXX', text)

            sentences = re.split(r'[.!?]+', text) #Then split

            #Then restore
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
        #Strips whitespace and filters out sentences shorter than 3 words as this would be headings

#Singleton instance - one shared with StylometryAnalyser object and used across whole app
stylometry_analyser = StylometryAnalyser()