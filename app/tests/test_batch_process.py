import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta
from uuid import uuid4

from app.routers.batch_process import (
    _run_batch,
    _is_cache_fresh,
    _batch_save_recommendations,
    _batch_status,
)

'''This details the mock versions used for testing'''

def make_mock_user(user_id=None):
    user = MagicMock()
    user.user_id = user_id or uuid4()
    return user

def make_mock_db():
    db = MagicMock()
    return db

'''These are test cases for the _is_cache_fresh function'''

class TestIsCacheFresh:

    #If a recommendation is generated within 24 hours, the cache is fresh 
    def test_returns_true_when_recent_recommendation_exists(self):
        db = make_mock_db()
        db.query.return_value.filter.return_value.first.return_value = (datetime.utcnow(),)
        result = _is_cache_fresh(uuid4(), db)
        assert result is True

    #If there are no recommendation within the 24 hours, then the cache is stale
    def test_returns_false_when_no_recent_recommendation(self):
        db = make_mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = _is_cache_fresh(uuid4(), db)
        assert result is False


'''These are test cases for the _batch_save_recommendations function'''

class TestBatchSaveRecommendations:

    #Any old recommendations for a user should be deleted before inserting new recommendations
    def test_clears_old_recommendations_before_saving(self):
        db = make_mock_db()
        user_id = uuid4()
        _batch_save_recommendations(user_id, [], db)
        db.query.return_value.filter.return_value.delete.assert_called_once()

    #Every scored book should be added to the database
    def test_saves_each_scored_book(self):
        db = make_mock_db()
        user_id = uuid4()
        scored = [
            {"book_id": str(uuid4()), "similarity": 0.9, "rank": 1},
            {"book_id": str(uuid4()), "similarity": 0.8, "rank": 2},
        ]
        _batch_save_recommendations(user_id, scored, db)
        assert db.add.call_count == 2
        db.commit.assert_called_once()

    #Even if there are no recommendations for a user, db.commit should be called
    def test_empty_scored_list_still_commits(self):
        db = make_mock_db()
        _batch_save_recommendations(uuid4(), [], db)
        db.commit.assert_called_once()

    #All recommendation should be saved with a rank starting at 1
    def test_ranks_are_assigned_sequentially(self):
        db = make_mock_db()
        saved_recs = []
        db.add.side_effect = lambda rec: saved_recs.append(rec)

        scored = [
            {"book_id": str(uuid4()), "similarity": 0.9},
            {"book_id": str(uuid4()), "similarity": 0.8},
            {"book_id": str(uuid4()), "similarity": 0.7},
        ]
        _batch_save_recommendations(uuid4(), scored, db)
        ranks = [r.rank for r in saved_recs]
        assert ranks == [1, 2, 3]

'''These are test cases for _batch_status'''

class TestBatchStatusDict:

    #Batch should not be running at the startup
    def test_initial_running_is_false(self):
        assert _batch_status["running"] is False

    #The status dict should have all the expected keys
    def test_has_required_keys(self):
        required_keys = [
            "running", "last_run", "last_run_user_count",
            "last_run_success_count", "last_run_error_count",
            "last_run_duration_seconds"
        ]
        for key in required_keys:
            assert key in _batch_status

    #All counters should start at 0
    def test_initial_counts_are_zero(self):
        assert _batch_status["last_run_user_count"] == 0
        assert _batch_status["last_run_success_count"] == 0
        assert _batch_status["last_run_error_count"] == 0

    #The last run should be none before the batch has run
    def test_initial_last_run_is_none(self):
        assert _batch_status["last_run"] is None


'''These are test cases for the _run_batch function'''

class TestRunBatch:

    #If a user has a fresh cache they should be skipped and not reprocessed
    def test_skips_user_when_cache_is_fresh(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._is_cache_fresh", return_value=True) as mock_fresh, \
             patch("app.routers.batch_process._score_candidates_for_user") as mock_score:

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            user = make_mock_user()
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = [user]

            _run_batch(batch_size=10, force_refresh=False)

            mock_score.assert_not_called()

    #If the force_refresh has been set to true then it should process users even if their cache is fresh
    def test_processes_user_when_force_refresh(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._is_cache_fresh", return_value=True), \
             patch("app.routers.batch_process._score_candidates_for_user", return_value=[]) as mock_score:

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            user = make_mock_user()
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = [user]

            _run_batch(batch_size=10, force_refresh=True)

            mock_score.assert_called_once()

    #If one user fails, the rest should still be processed
    def test_single_user_failure_does_not_abort_batch(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._is_cache_fresh", return_value=False), \
             patch("app.routers.batch_process._score_candidates_for_user",
                   side_effect=RuntimeError("fail")):

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            users = [make_mock_user(), make_mock_user(), make_mock_user()]
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = users

            _run_batch(batch_size=10, force_refresh=False)

    #A per-user execption should trigger a db.rollback()
    def test_failed_user_triggers_rollback(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._is_cache_fresh", return_value=False), \
             patch("app.routers.batch_process._score_candidates_for_user",
                   side_effect=RuntimeError("boom")):

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = [make_mock_user()]

            _run_batch(batch_size=10, force_refresh=False)

            mock_db.rollback.assert_called()

    #If no users are in the database, it should complete gracefully
    def test_empty_user_list_completes_without_error(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._score_candidates_for_user") as mock_score:

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = []

            _run_batch(batch_size=10, force_refresh=False)
            mock_score.assert_not_called()

    #The _batch_status should reflect completion after _run_batch is finised
    def test_status_updated_after_run(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._score_candidates_for_user", return_value=[]):

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = []

            _run_batch(batch_size=10, force_refresh=False)

            assert _batch_status["running"] is False
            assert _batch_status["last_run"] is not None

    #db.close() should always be called even if an error occurs
    def test_db_closed_after_run(self):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._score_candidates_for_user", return_value=[]):

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = []

            _run_batch(batch_size=10, force_refresh=False)

            mock_db.close.assert_called_once()


'''These are test cases for the batch size'''

class TestBatchSizeBoundaries:

    def _run_with_n_users(self, n):
        with patch("app.routers.batch_process.SessionLocal") as mock_session, \
             patch("app.routers.batch_process._is_cache_fresh", return_value=False), \
             patch("app.routers.batch_process._score_candidates_for_user", return_value=[]):

            mock_db = make_mock_db()
            mock_session.return_value = mock_db
            users = [make_mock_user() for _ in range(n)]
            mock_db.query.return_value.join.return_value.distinct.return_value.limit.return_value.all.return_value = users
            _run_batch(batch_size=n or 1, force_refresh=False)

    def test_batch_size_of_1(self):
        self._run_with_n_users(1)

    def test_batch_size_of_10(self):
        self._run_with_n_users(10)

    def test_batch_size_of_100(self):
        self._run_with_n_users(100)

    def test_batch_size_zero_users(self):
        self._run_with_n_users(0)