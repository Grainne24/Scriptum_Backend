import pytest
from app.services.stylometry_service import stylometry_analyser

#The Sun Also Rises by Ernest Hemmingway snippet
HEMINGWAY_STYLE = (
    "In the morning I walked down the Boulevard to the rue Soufflot for coffee and brioche. It was a fine morning. The horse-chestnut trees in the Luxembourg gardens were in bloom. There was the pleasant early-morning feeling of a hot day. I read the papers with the coffee and then smoked a cigarette. The flower-women were coming up from the market and arranging their daily stock. The taxi-cabs were going in the other direction. I walked on past the tables and into the street. The bus was crowded and I had to stand. The conductor punched my ticket and I stood on the platform. At the next stop a girl got on. She was carrying a heavy bag. She looked tired. The morning light was hard on her face. I looked away. At the terminus I got off and walked toward the river. The water was high and brown. Two fishermen sat on the bank. They did not speak. A dog came by and sniffed at their bait pail. One of the men kicked at the dog. The dog moved away and lay down in the sun. I crossed the bridge and walked up the hill into the old part of town. The streets were narrow and the houses were old and the stones were worn smooth. A woman emptied a bucket from a window above me. I stepped back against the wall. She did not look down. I walked on up the hill. At the top there was a cafe with tables outside. I sat down and ordered a coffee. The waiter was old and slow. He brought the coffee and I paid him. I sat and watched the street. A cat came around the corner and sat in the sun. It licked its paw and then looked at me. I looked back. The cat got up and walked away. I finished the coffee and left a tip on the table and walked back down the hill toward the river. The sun was higher now and it was getting warm. I took off my jacket and carried it."
) * 4

#Pride and Prejeduce by Jane Austen snippet
AUSTEN_STYLE = (
    "It is a truth universally acknowledged that a single man in possession of a good fortune must be in want of a wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered the rightful property of some one or other of their daughters. My dear Mr. Bennet, said his lady to him one day, have you heard that Netherfield Park is let at last? Mr. Bennet replied that he had not. But it is, returned she, for Mrs. Long has just been here, and she told me all about it. Mr. Bennet made no answer. Do you not want to know who has taken it? cried his wife impatiently. You want to tell me, and I have no objection to hearing it. This was invitation enough. Why, my dear, you must know, Mrs. Long says that Netherfield is taken by a young man of large fortune from the north of England; that he came down on Monday in a chaise and four to see the place, and was so much delighted with it, that he agreed with Mr. Morris immediately; that he is to take possession before Michaelmas, and some of his servants are to be in the house by the end of next week. What is his name? Bingley. Is he married or single? Oh! Single, my dear, to be sure! A single man of large fortune; four or five thousand a year. What a fine thing for our girls! How so? Can it affect them? My dear Mr. Bennet, replied his wife, how can you be so tiresome! You must know that I am thinking of his marrying one of them. Is that his design in settling here? Design! Nonsense, how can you talk so! But it is very likely that he may fall in love with one of them, and therefore you must visit him as soon as he comes. I see no occasion for that. You and the girls may go, or you may send them by themselves, which perhaps will be still better, for as you are as handsome as any of them, Mr. Bingley may like you the best of the party."
) * 4

'''All test cases for stylometry_analyser'''

class TestAnalyseText:
    
    #This checks to see if every expected key is present in the analysis result
    def test_returns_all_required_fields(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        required = [
            "pacing_score", "tone_score", "vocabulary_richness",
            "avg_sentence_length", "avg_word_length", "lexical_diversity",
            "total_words", "total_sentences", "unique_words"
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    #This makes sure all score fields return numbers
    def test_scores_are_numeric(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        for key in ["pacing_score", "tone_score", "vocabulary_richness",
                    "avg_sentence_length", "avg_word_length", "lexical_diversity"]:
            assert isinstance(result[key], (int, float)), f"{key} is not numeric"

    #This makes sure the pacing score is in the range of 1-100
    def test_pacing_score_in_range(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        assert 0 <= result["pacing_score"] <= 100

    #This makes sure the tone score is in the range of 1-100
    def test_tone_score_in_range(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        assert 0 <= result["tone_score"] <= 100

    #This makes sure the lexical diversity score is between 0-1
    def test_lexical_diversity_between_0_and_1(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        assert 0 <= result["lexical_diversity"] <= 1

    #This makes sure real text always produces a word count greater than 0
    def test_total_words_is_positive(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        assert result["total_words"] > 0

    #This makes sure you can never have more unique words than total words
    def test_unique_words_lte_total_words(self):
        result = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        assert result["unique_words"] <= result["total_words"]

    #This tests to see if short sentences score higher for pacing than long complex ones
    def test_short_sentences_give_high_pacing(self):
        short = ("Go. Run. Stop. Look. Wait. Jump. Fall. Rise. " * 100)
        long  = (
            "The extraordinarily complex and deeply philosophical question of what constitutes human happiness remains fundamentally unresolved despite centuries of careful scholarly inquiry and debate. " * 40
        )
        short_result = stylometry_analyser.analyse_text(short)
        long_result  = stylometry_analyser.analyse_text(long)
        assert short_result["pacing_score"] > long_result["pacing_score"]

    #Text using repitive words should score low on lexical diveristy
    def test_repeated_text_has_low_lexical_diversity(self):
        repetitive = "the cat sat on the mat " * 200
        result = stylometry_analyser.analyse_text(repetitive)
        assert result["lexical_diversity"] < 0.3

    #text with many different words scores high on vocab richness
    def test_varied_vocabulary_has_high_richness(self):
        import random, string
        words = [
            ''.join(random.choices(string.ascii_lowercase, k=6))
            for _ in range(500)
        ]
        varied_text = '. '.join(' '.join(words[i:i+5]) for i in range(0, 500, 5))
        result = stylometry_analyser.analyse_text(varied_text)
        assert result["vocabulary_richness"] > 0.5

    #Passing an empty string should raise a ValueError
    def test_empty_text_does_not_crash(self):
        with pytest.raises(ValueError, match="Text cannot be empty"):
            stylometry_analyser.analyse_text("")

    #This ensures different styles produce differnt scores e.g. Hemmingway and Austen should produce different scores
    def test_different_styles_produce_different_scores(self):
        r1 = stylometry_analyser.analyse_text(HEMINGWAY_STYLE)
        r2 = stylometry_analyser.analyse_text(AUSTEN_STYLE)
        assert r1["avg_sentence_length"] != r2["avg_sentence_length"]

'''These are all tests for aimilarity calculation for book texts'''

class TestCalculateSimilarity:

    #When a book is compared against a copy of itself it should return a positive similarity score
    def test_identical_texts_return_high_similarity(self):
        seed = {"author": "Hemingway", "title": "Book A", "text": HEMINGWAY_STYLE}
        candidates = [
            {"author": "Hemingway Copy", "title": "Book B", "text": HEMINGWAY_STYLE},
            {"author": "Austen", "title": "Book C", "text": AUSTEN_STYLE},
        ]
        results = stylometry_analyser.get_recommendations(seed, candidates, top_n=2)
        top_result = results[0]
        assert top_result["similarity"] > 0.0

    #Checks to see if similar books will rank closer than a stylitically different book
    def test_similar_style_scores_higher_than_different(self):
        seed = {"author": "Hemingway", "title": "Book A", "text": HEMINGWAY_STYLE}
        candidates = [
            {"author": "Hemingway B", "title": "Book B", "text": HEMINGWAY_STYLE[:len(HEMINGWAY_STYLE)//2]},
            {"author": "Austen", "title": "Book C", "text": AUSTEN_STYLE},
        ]
        results = stylometry_analyser.get_recommendations(seed, candidates, top_n=2)
        titles = [r["title"] for r in results]
        assert titles.index("Book B") < titles.index("Book C")

    #This makes sure all similarity score are in the range 0-1
    def test_similarity_is_between_0_and_1(self):
        seed = {"author": "Hemingway", "title": "Book A", "text": HEMINGWAY_STYLE}
        candidates = [
            {"author": "Hemingway B", "title": "Book B", "text": HEMINGWAY_STYLE},
            {"author": "Austen", "title": "Book C", "text": AUSTEN_STYLE},
        ]
        results = stylometry_analyser.get_recommendations(seed, candidates, top_n=2)
        for r in results:
            assert 0.0 <= r["similarity"] <= 1.0

'''These are all tests for Burrows Delta directly via calculate_delta_between_two'''

class TestRecommenderVsBurrowsDelta:

    #Tests my personal recommender against burrows delta
    def test_recommender_agrees_with_burrows_delta_ranking(self):
        
        #Use Burrows Delta to rank Hemingway vs Austen against seed
        seed = {"author": "Hemingway", "title": "Seed", "text": HEMINGWAY_STYLE}
        candidates = [
            {"author": "Hemingway2", "title": "Similar", "text": HEMINGWAY_STYLE},
            {"author": "Austen", "title": "Different", "text": AUSTEN_STYLE},
        ]
        burrows_results = stylometry_analyser.get_recommendations(seed, candidates, top_n=2)
        burrows_top = burrows_results[0]["title"]

        #Use feature vector distance (what the personalised recommender uses) to rank the same books
        from app.feedback_weights import calculate_stylometric_distance
        from unittest.mock import MagicMock

        def make_profile(text):
            result = stylometry_analyser.analyse_text(text)
            profile = MagicMock()
            profile.pacing_score = result["pacing_score"]
            profile.tone_score = result["tone_score"]
            profile.vocabulary_richness = result["vocabulary_richness"]
            profile.avg_sentence_length = result["avg_sentence_length"]
            profile.avg_word_length = result["avg_word_length"]
            profile.lexical_diversity = result["lexical_diversity"]
            return profile

        seed_profile = make_profile(HEMINGWAY_STYLE)
        similar_profile = make_profile(HEMINGWAY_STYLE)
        different_profile = make_profile(AUSTEN_STYLE)

        similar_score = calculate_stylometric_distance(seed_profile, similar_profile)
        different_score = calculate_stylometric_distance(seed_profile, different_profile)

        feature_top = "Similar" if similar_score > different_score else "Different"

        #Both methods should agree on which book is more similar
        assert burrows_top == feature_top, (
            f"Burrows Delta ranked '{burrows_top}' first but "
            f"feature vector ranked '{feature_top}' first"
        )