import pytest
from app.feedback_weights import (
    get_rating_weight,
    calculate_stylometric_distance,
    calculate_feedback_adjustment,
)

'''These are test cases for the get_rating_weight function - Boundary'''

class TestRatingWeightBoundaries:

    #A rating of 1 is the lowest rating and this should return -2
    def test_minimum_valid_rating(self):
        assert get_rating_weight(1) == -2

    #A rating of 5 is the highest rating and should return +2
    def test_maximum_valid_rating(self):
        assert get_rating_weight(5) == 2

    #A rating of 0 is out of range and should just return a neutral weight
    def test_rating_just_below_minimum(self):
        assert get_rating_weight(0) == 0

    #A half rating should round up and return +2
    def test_half_star_rounds_to_nearest(self):
        assert get_rating_weight(4.5) == 2
 
    #A exactly half way rating should return a neutral 0
    def test_exactly_halfway_float(self):
        assert get_rating_weight(2.5) == 0

    #A null rating should not crash the systema and just return 0
    def test_none_rating_does_not_crash(self):
        result = get_rating_weight(None)
        assert result == 0


'''These are test cases for the calculate_stylometric_distance function - Boundary'''

class MockProfile:
    def __init__(self, pacing=50.0, tone=50.0, vocab=50.0,
                sentence_len=20.0, word_len=5.0, diversity=0.5):
        self.pacing_score = pacing
        self.tone_score = tone
        self.vocabulary_richness = vocab
        self.avg_sentence_length = sentence_len
        self.avg_word_length = word_len
        self.lexical_diversity = diversity

class TestStylometricDistanceBoundaries:
 
    #The same profile compared to itself should return that they are the most similar
    def test_identical_profiles_similarity_is_1(self):
        p = MockProfile()
        assert calculate_stylometric_distance(p, p) == pytest.approx(1.0, abs=0.01)
 
    #Profiles that are extremely different to each other should return a low similarity score
    def test_maximum_distance_profiles(self):
        low = MockProfile(pacing=0, tone=0, vocab=0, sentence_len=0, word_len=0, diversity=0)
        high = MockProfile(pacing=100, tone=100, vocab=100, sentence_len=50, word_len=10, diversity=1.0)
        result = calculate_stylometric_distance(low, high)
        assert result < 0.2
 
    #Similarity scores should also be in the range of 0-1
    def test_result_always_between_0_and_1(self):
        a = MockProfile(pacing=10, tone=90, vocab=30)
        b = MockProfile(pacing=80, tone=20, vocab=70)
        result = calculate_stylometric_distance(a, b)
        assert 0.0 <= result <= 1.0
 
    #All of the zero profiles should return a division error
    def test_all_zero_profiles_do_not_crash(self):
        zero = MockProfile(pacing=0, tone=0, vocab=0, sentence_len=0, word_len=0, diversity=0)
        result = calculate_stylometric_distance(zero, zero)
        assert result == pytest.approx(1.0, abs=0.01)
 
    #Even if a singular feature differs it should still return a high similarity score
    def test_single_feature_difference(self):
        base = MockProfile()
        different = MockProfile(pacing=100)
        result = calculate_stylometric_distance(base, different)
        assert result > 0.5
 
    #The distance between A and B profiles should be equal distance to B and A
    def test_symmetry(self):
        a = MockProfile(pacing=30, tone=70)
        b = MockProfile(pacing=80, tone=20)
        assert calculate_stylometric_distance(a, b) == pytest.approx(
            calculate_stylometric_distance(b, a), abs=0.001
        )

'''These are test cases for the calculate_feedback_adjustment function - Edge'''

def make_rated(rating, profile):
    return {"rating": rating, "profile": profile}

class TestFeedbackAdjustmentEdgeCases:

    #No rated books should return 0 and not crash
    def test_empty_rated_books_returns_zero(self):
        candidate = MockProfile()
        result = calculate_feedback_adjustment(candidate, [])
        assert result == 0.0
 
    #One highly-rated similar book should be given a positive adjustment
    def test_single_rated_book_positive(self):
        candidate = MockProfile(pacing=50, tone=50)
        rated_book = make_rated(5, MockProfile(pacing=50, tone=50))
        result = calculate_feedback_adjustment(candidate, [rated_book])
        assert result > 0

    #One low-rated similar book should be given a negative adjustment
    def test_single_rated_book_negative(self):
        candidate = MockProfile(pacing=50, tone=50)
        rated_book = make_rated(1, MockProfile(pacing=50, tone=50))
        result = calculate_feedback_adjustment(candidate, [rated_book])
        assert result < 0

    #A 3-star rating should produce a almost zero adjustment
    def test_neutral_rating_has_minimal_effect(self):
        candidate = MockProfile()
        rated_book = make_rated(3, MockProfile())
        result = calculate_feedback_adjustment(candidate, [rated_book])
        assert abs(result) < 0.05

    #A large number rated books should not crash the system
    def test_many_rated_books_does_not_crash(self):
        candidate = MockProfile()
        rated_books = [
            make_rated((i % 5) + 1, MockProfile(pacing=float(i)))
            for i in range(200)
        ]
        result = calculate_feedback_adjustment(candidate, rated_books)
        assert isinstance(result, float)

    #An equal mix of 1 and 5 star rating on books with the same stylometric profile should cancel out
    def test_opposing_ratings_cancel_out(self):
        candidate = MockProfile(pacing=50, tone=50)
        high = make_rated(5, MockProfile(pacing=50, tone=50))
        low = make_rated(1, MockProfile(pacing=50, tone=50))
        result = calculate_feedback_adjustment(candidate, [high, low])
        assert abs(result) < 0.5

    #A book with different style should influence less thn a similar one
    def test_dissimilar_book_has_less_influence(self):
        candidate = MockProfile(pacing=50, tone=50)
        similar = make_rated(5, MockProfile(pacing=50, tone=50))
        dissimilar = make_rated(5, MockProfile(pacing=0, tone=0))
        similar_adj = calculate_feedback_adjustment(candidate, [similar])
        dissimilar_adj = calculate_feedback_adjustment(candidate, [dissimilar])
        assert similar_adj > dissimilar_adj

    #Any rated book with no stylometric profile shoud just be skipped
    def test_rated_book_with_none_profile_does_not_crash(self):
        candidate = MockProfile()
        rated_book = make_rated(5, None)
        try:
            result = calculate_feedback_adjustment(candidate, [rated_book])
            assert isinstance(result, float)
        except Exception as e:
            pytest.fail(f"Should not raise: {e}")