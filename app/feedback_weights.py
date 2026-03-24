RATING_WEIGHTS = {
    1: -2,
    2: -1,
    3:  0,
    4:  1,
    5:  2,
}

def get_rating_weight(rating: float) -> int:
    return RATING_WEIGHTS.get(round(rating), 0)

def calculate_stylometric_distance(profile_a, profile_b) -> float:
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

        diff = abs(float(val_a) - float(val_b)) / scale
        similarity = max(0.0, 1.0 - diff)
        total_similarity += similarity
        count += 1

    return total_similarity / count if count > 0 else 0.0


def calculate_feedback_adjustment(
    candidate_profile,
    user_rated_books: list, 
) -> float:
    if not user_rated_books:
        return 0.0

    total_adjustment = 0.0

    for item in user_rated_books:
        rated_profile = item["profile"]
        rating = float(item["rating"])
        
        weight = get_rating_weight(rating)
        if weight == 0:
            continue

        similarity = calculate_stylometric_distance(candidate_profile, rated_profile)
        total_adjustment += similarity * weight

    scaled = total_adjustment / len(user_rated_books)

    return scaled