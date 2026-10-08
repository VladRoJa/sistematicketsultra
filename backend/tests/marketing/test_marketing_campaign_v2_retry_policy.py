from datetime import datetime, timedelta, timezone

from app.services import marketing_campaign_v2_retry_policy as policy


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


def test_first_retry_is_immediate_after_manual_confirmation():
    assert policy.next_retry_allowed_at(
        completed_attempts=0,
        resolved_at=NOW,
    ) == NOW


def test_second_retry_waits_sixty_seconds():
    assert policy.next_retry_allowed_at(
        completed_attempts=1,
        resolved_at=NOW,
    ) == NOW + timedelta(seconds=60)


def test_third_retry_waits_five_minutes():
    assert policy.next_retry_allowed_at(
        completed_attempts=2,
        resolved_at=NOW,
    ) == NOW + timedelta(seconds=300)


def test_three_completed_attempts_is_exhausted():
    assert policy.retry_is_exhausted(3) is True
    assert policy.next_retry_allowed_at(
        completed_attempts=3,
        resolved_at=NOW,
    ) is None


def test_negative_attempts_are_normalized_for_policy():
    assert policy.retry_is_exhausted(-1) is False
    assert policy.next_retry_allowed_at(
        completed_attempts=-1,
        resolved_at=NOW,
    ) == NOW
