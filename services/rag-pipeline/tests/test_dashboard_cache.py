"""Tests for the dashboard TTL cache (rag_pipeline.dashboard_cache) and its
wiring into get_dashboard_summary/get_recent_activity/invalidate_dashboard_cache.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_pipeline import dashboard, dashboard_cache
from rag_pipeline.dashboard import get_dashboard_summary, get_recent_activity
from rag_pipeline.dashboard_cache import invalidate_dashboard_cache
from rag_pipeline.documents import delete_document
from rag_pipeline.ingest import create_pending_document, process_document

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _seed_transaction(fake_supabase, user_id: str = USER_ID, **overrides):
    row = {
        "id": overrides.pop("id", None) or f"tx-{len(fake_supabase.tables.get('transactions', []))}",
        "document_id": "doc-1",
        "user_id": user_id,
        # Within the current month-to-date window (see
        # dashboard._month_to_date_span) so it counts toward total_income,
        # not just transaction_count.
        "occurred_on": _today_iso(),
        "amount": "100.00",
        "category": "Uncategorized",
        "description": "",
    }
    row.update(overrides)
    fake_supabase.tables.setdefault("transactions", []).append(row)
    return row


def test_second_summary_call_within_ttl_does_not_requery(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase)
    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")

    first = get_dashboard_summary(USER_ID, settings=fake_settings)
    second = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 1
    assert second == first


def test_summary_requeries_after_invalidation(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase)
    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")

    first = get_dashboard_summary(USER_ID, settings=fake_settings)
    _seed_transaction(fake_supabase, amount="500.00")
    invalidate_dashboard_cache(USER_ID)
    second = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 2
    assert second.total_income == 600.00
    assert second != first


def test_second_activity_call_within_ttl_does_not_requery(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase)
    compute_spy = mocker.spy(dashboard, "_compute_recent_activity")

    first = get_recent_activity(USER_ID, settings=fake_settings)
    second = get_recent_activity(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 1
    assert second == first


def test_activity_requeries_after_invalidation(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase, id="tx-first")
    compute_spy = mocker.spy(dashboard, "_compute_recent_activity")

    first = get_recent_activity(USER_ID, settings=fake_settings)
    _seed_transaction(fake_supabase, id="tx-second", occurred_on="2099-01-01")
    invalidate_dashboard_cache(USER_ID)
    second = get_recent_activity(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 2
    assert [tx.id for tx in first] == ["tx-first"]
    assert [tx.id for tx in second] == ["tx-second", "tx-first"]


def test_first_ever_activity_call_for_a_user_survives_a_concurrent_invalidation(
    fake_supabase, fake_settings, mocker
):
    """Integration-level regression test wiring `cached_activity`'s real
    `prefix=user_id` argument through to `_TTLCache`: a user's very first
    `get_recent_activity` call (no prior cache entry for this `user_id` at
    all) that races a concurrent `invalidate_dashboard_cache(user_id)` call
    (e.g. that same user uploading/deleting a document mid-request) must not
    leave the stale, pre-invalidation result cached afterwards.
    """
    _seed_transaction(fake_supabase, id="tx-stale")
    real_compute = dashboard._compute_recent_activity

    def compute_that_races_an_invalidation(user_id, limit, settings=None):
        # Simulate the concurrent write's invalidation landing while this
        # (first-ever, for this user) compute() call is still in flight.
        invalidate_dashboard_cache(USER_ID)
        return real_compute(user_id, limit, settings)

    compute_mock = mocker.patch(
        "rag_pipeline.dashboard._compute_recent_activity",
        side_effect=compute_that_races_an_invalidation,
    )

    first = get_recent_activity(USER_ID, settings=fake_settings)
    assert [tx.id for tx in first] == ["tx-stale"]

    # A fresh transaction lands after the racing invalidation "commits".
    _seed_transaction(fake_supabase, id="tx-fresh", occurred_on="2099-01-01")
    second = get_recent_activity(USER_ID, settings=fake_settings)

    # The second call must be a genuine re-query (cache miss), not a hit on
    # the stale result written by the first, racing compute() call.
    assert compute_mock.call_count == 2
    assert [tx.id for tx in second] == ["tx-fresh", "tx-stale"]


def test_summary_and_activity_caches_are_independent(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase)
    summary_spy = mocker.spy(dashboard, "_compute_dashboard_summary")
    activity_spy = mocker.spy(dashboard, "_compute_recent_activity")

    get_dashboard_summary(USER_ID, settings=fake_settings)
    get_recent_activity(USER_ID, settings=fake_settings)
    # Repeat both - each should have hit its own cache, not the other's.
    get_dashboard_summary(USER_ID, settings=fake_settings)
    get_recent_activity(USER_ID, settings=fake_settings)

    assert summary_spy.call_count == 1
    assert activity_spy.call_count == 1


def test_invalidating_one_user_does_not_evict_the_other(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase, user_id=USER_ID)
    _seed_transaction(fake_supabase, user_id=OTHER_USER_ID)
    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")

    get_dashboard_summary(USER_ID, settings=fake_settings)
    get_dashboard_summary(OTHER_USER_ID, settings=fake_settings)
    assert compute_spy.call_count == 2

    invalidate_dashboard_cache(USER_ID)

    # OTHER_USER_ID's entry must still be cached (not evicted by USER_ID's
    # invalidation) - a repeat call for it must not re-query.
    get_dashboard_summary(OTHER_USER_ID, settings=fake_settings)
    assert compute_spy.call_count == 2

    # USER_ID's entry was evicted, so its repeat call must re-query.
    get_dashboard_summary(USER_ID, settings=fake_settings)
    assert compute_spy.call_count == 3


def test_different_users_do_not_share_a_summary_cache_entry(fake_supabase, fake_settings):
    _seed_transaction(fake_supabase, user_id=USER_ID, amount="100.00")
    _seed_transaction(fake_supabase, user_id=OTHER_USER_ID, amount="999.00")

    summary_a = get_dashboard_summary(USER_ID, settings=fake_settings)
    summary_b = get_dashboard_summary(OTHER_USER_ID, settings=fake_settings)

    assert summary_a.total_income == 100.00
    assert summary_b.total_income == 999.00


def test_different_users_do_not_share_an_activity_cache_entry(fake_supabase, fake_settings):
    _seed_transaction(fake_supabase, id="tx-mine", user_id=USER_ID)
    _seed_transaction(fake_supabase, id="tx-theirs", user_id=OTHER_USER_ID)

    activity_a = get_recent_activity(USER_ID, settings=fake_settings)
    activity_b = get_recent_activity(OTHER_USER_ID, settings=fake_settings)

    assert [tx.id for tx in activity_a] == ["tx-mine"]
    assert [tx.id for tx in activity_b] == ["tx-theirs"]


def test_create_pending_document_invalidates_cached_summary(fake_supabase, fake_settings, mocker):
    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")

    before = get_dashboard_summary(USER_ID, settings=fake_settings)
    assert before.total_document_count == 0

    create_pending_document("statement.pdf", USER_ID, settings=fake_settings)
    after = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 2
    assert after.total_document_count == 1


def test_process_document_success_invalidates_cached_summary(
    fake_supabase, fake_settings, fake_embeddings, tmp_path, mocker
):
    document_id = create_pending_document("statement.csv", USER_ID, settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text("Date,Description,Category,Amount\n2026-01-15,Coffee,Dining,-4.50\n")

    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")
    before = get_dashboard_summary(USER_ID, settings=fake_settings)
    assert before.document_count == 0
    assert before.transaction_count == 0

    process_document(document_id, csv_path, USER_ID, settings=fake_settings)
    after = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 2
    assert after.document_count == 1
    assert after.transaction_count == 1


def test_process_document_failure_invalidates_cached_summary(
    fake_supabase, fake_settings, mocker, tmp_path
):
    document_id = create_pending_document("broken.pdf", USER_ID, settings=fake_settings)
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"not a real pdf")
    mocker.patch("rag_pipeline.ingest.parse_document", side_effect=ValueError("boom"))

    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")
    get_dashboard_summary(USER_ID, settings=fake_settings)

    with pytest.raises(ValueError, match="boom"):
        process_document(document_id, pdf_path, USER_ID, settings=fake_settings)

    get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 2


def test_delete_document_invalidates_cached_summary(fake_supabase, fake_settings, mocker):
    document_id = create_pending_document("statement.pdf", USER_ID, settings=fake_settings)
    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")

    before = get_dashboard_summary(USER_ID, settings=fake_settings)
    assert before.total_document_count == 1

    delete_document(document_id, USER_ID, settings=fake_settings)
    after = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 2
    assert after.total_document_count == 0


def test_delete_document_no_op_does_not_invalidate(fake_supabase, fake_settings, mocker):
    document_id = create_pending_document("theirs.pdf", OTHER_USER_ID, settings=fake_settings)
    get_dashboard_summary(USER_ID, settings=fake_settings)
    compute_spy = mocker.spy(dashboard, "_compute_dashboard_summary")

    # Attempting to delete another user's document is a no-op (returns
    # False) - it must not evict USER_ID's unrelated cached entry.
    deleted = delete_document(document_id, USER_ID, settings=fake_settings)
    assert deleted is False

    get_dashboard_summary(USER_ID, settings=fake_settings)

    assert compute_spy.call_count == 0


def test_process_document_invalidates_before_attempting_failure_status_update(
    fake_supabase, fake_settings, mocker, tmp_path
):
    """Regression test for a cascading-double-failure edge case: if the
    "processing" work itself fails *and* the subsequent
    `_mark_failed_with_message` call also fails (e.g. Supabase is having an
    outage), invalidation must still have happened before either exception
    propagates - it must not be skipped just because the failure-status
    update itself blew up.
    """
    document_id = create_pending_document("statement.csv", USER_ID, settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text("Date,Description,Category,Amount\n2026-01-15,Coffee,Dining,-4.50\n")

    mocker.patch(
        "rag_pipeline.ingest.parse_document", side_effect=RuntimeError("original failure")
    )
    mocker.patch(
        "rag_pipeline.ingest._mark_failed_with_message",
        side_effect=RuntimeError("mark-failed also failed"),
    )
    invalidate_spy = mocker.patch("rag_pipeline.ingest.invalidate_dashboard_cache")

    with pytest.raises(RuntimeError, match="mark-failed also failed"):
        process_document(document_id, csv_path, USER_ID, settings=fake_settings)

    invalidate_spy.assert_called_once_with(USER_ID)


def test_ttlcache_discards_stale_write_from_compute_in_flight_during_invalidation():
    """Regression test for a write-after-invalidate race: a `compute()` call
    that read data before a key was invalidated must not "un-invalidate"
    the entry afterwards by writing that stale value back with a fresh TTL.
    """
    cache = dashboard_cache._TTLCache(ttl_seconds=30.0)

    def compute_that_invalidates_mid_flight():
        # Simulates a write (and its invalidation) happening concurrently
        # while this (slow) compute call is still in flight.
        cache.invalidate("k")
        return "stale-value-read-before-invalidation"

    result = cache.get_or_compute("k", compute_that_invalidates_mid_flight)

    # The caller that triggered this specific compute still gets its value.
    assert result == "stale-value-read-before-invalidation"
    # But the cache write must have been discarded: the next lookup must be
    # a genuine cache miss, not a hit on the stale value.
    assert cache.get_or_compute("k", lambda: "fresh-value") == "fresh-value"


def test_ttlcache_invalidate_prefix_discards_stale_write_for_never_before_seen_key():
    """Regression test for a gap in the generation-guard: `invalidate_prefix`
    can't retroactively bump a per-key generation for a concrete
    `"{prefix}:{suffix}"` key it has never tracked before (e.g. a user's
    first-ever `get_recent_activity` call for a given `limit` racing with
    that same user concurrently uploading/deleting a document). The
    per-prefix epoch must catch this even though the per-key generation
    can't.
    """
    cache = dashboard_cache._TTLCache(ttl_seconds=30.0)

    def compute_that_invalidates_prefix_mid_flight():
        # Simulates a concurrent invalidate_dashboard_cache(user_id) call
        # (which calls invalidate_prefix on the activity cache) happening
        # while this key's first-ever compute() is still in flight.
        cache.invalidate_prefix("user1")
        return "stale-value-read-before-invalidation"

    # "user1:20" has never been accessed before this call - there is no
    # existing entry or generation to invalidate directly.
    result = cache.get_or_compute(
        "user1:20", compute_that_invalidates_prefix_mid_flight, prefix="user1"
    )

    assert result == "stale-value-read-before-invalidation"
    # The stale write must have been discarded via the prefix epoch check,
    # not silently re-cached with a fresh TTL.
    assert cache.get_or_compute("user1:20", lambda: "fresh-value", prefix="user1") == (
        "fresh-value"
    )


def test_ttlcache_invalidate_prefix_avoids_key_collisions():
    """Regression test: invalidating prefix "abc" must evict "abc" and
    "abc:20" but never "abc2:20" - matching is prefix-plus-separator, not a
    bare string prefix.
    """
    cache = dashboard_cache._TTLCache(ttl_seconds=30.0)
    cache.get_or_compute("abc", lambda: "abc-value")
    cache.get_or_compute("abc:20", lambda: "abc-20-value")
    cache.get_or_compute("abc2:20", lambda: "abc2-20-value")

    cache.invalidate_prefix("abc")

    assert cache.get_or_compute("abc", lambda: "recomputed-abc") == "recomputed-abc"
    assert cache.get_or_compute("abc:20", lambda: "recomputed-abc-20") == "recomputed-abc-20"
    # "abc2:20" must survive untouched.
    assert cache.get_or_compute("abc2:20", lambda: "should-not-run") == "abc2-20-value"


def test_reset_for_tests_clears_both_caches(fake_supabase, fake_settings, mocker):
    _seed_transaction(fake_supabase)
    summary_spy = mocker.spy(dashboard, "_compute_dashboard_summary")
    activity_spy = mocker.spy(dashboard, "_compute_recent_activity")

    get_dashboard_summary(USER_ID, settings=fake_settings)
    get_recent_activity(USER_ID, settings=fake_settings)

    dashboard_cache.reset_for_tests()

    get_dashboard_summary(USER_ID, settings=fake_settings)
    get_recent_activity(USER_ID, settings=fake_settings)

    assert summary_spy.call_count == 2
    assert activity_spy.call_count == 2
