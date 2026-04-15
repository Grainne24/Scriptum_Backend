'''
This file procides the rating to weight mapping and two scoring functions used by recommendation pipeline in batch_process.py
'''

#Maps star ratings to influence weights used in calculcate_feedback_adjustment
RATING_WEIGHTS = {
    1: -2,
    2: -1,
    3:  0,
    4:  1,
    5:  2,
}

def get_rating_weight(rating) -> int:
#Converts raw star rating to integer influence weight - rounds to neared integer
    if rating is None:
        return 0
    try:
        rounded = int(rating + 0.5)
        return RATING_WEIGHTS.get(rounded, 0)
    except (TypeError, ValueError):
        return 0

def calculate_stylometric_distance(profile_a, profile_b) -> float:
#Computes stylometric similarity score between 2 stylometricProfile objects 
    '''
    Normalised by scale vector
    Feature scale factors:
            pacing_score / 100.0 -action verb density score (0-100 range)
            tone_score / 100.0 -lexicon-based tone score (0-100 range)
            vocabulary_richness / 100.0 -sliding window TTR (0-100 range)
            avg_sentence_length / 50.0 -typical range ~5-50 words per sentence
            avg_word_length /  10.0 -typical range ~3-10 characters per word
            lexical_diversity / 1.0 -already normalised to (0, 1]
    '''
    features = [
        ("pacing_score", 100.0),
        ("tone_score", 100.0),
        ("vocabulary_richness", 100.0),
        ("avg_sentence_length", 50.0),
        ("avg_word_length", 10.0),
        ("lexical_diversity", 1.0),
    ]

    total_similarity = 0.0
    count = 0

    for attr, scale in features:
        val_a = getattr(profile_a, attr, None)
        val_b = getattr(profile_b, attr, None)

        if val_a is None or val_b is None:
            continue

        #Clamp at 0.0 so values further apart than the scale don't go negative.
        diff = abs(float(val_a) - float(val_b)) / scale
        similarity = max(0.0, 1.0 - diff)
        total_similarity += similarity
        count += 1

    #Return the mean similarity across valid features else return 0
    return total_similarity / count if count > 0 else 0.0


def calculate_feedback_adjustment(candidate_profile,user_rated_books: list) -> float:
#This computes a feedback adjustment score for a candidate book based on how stylistically similar it is to books the user has already rated.
    if not user_rated_books:
        return 0.0

    total_adjustment = 0.0

    for item in user_rated_books:
        rated_profile = item["profile"]
        rating = float(item["rating"])
        
        weight = get_rating_weight(rating)
        if weight == 0:
            continue #3 star ratings are neutral so skip

        #High similairity contributes +2 and low similarity contributes +2
        similarity = calculate_stylometric_distance(candidate_profile, rated_profile)
        total_adjustment += similarity * weight

    #Average across all rated books so adjustments dont grow too big as a user rates more books
    scaled = total_adjustment / len(user_rated_books)

    return scaled