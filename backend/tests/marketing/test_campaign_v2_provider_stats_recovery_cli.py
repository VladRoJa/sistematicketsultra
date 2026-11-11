from unittest.mock import MagicMock, patch

import pytest

from scripts.marketing.capture_campaign_v2_stats import run


def test_preview_does_not_call_provider_or_modify_database():
    session = MagicMock()
    with patch("scripts.marketing.capture_campaign_v2_stats.candidate_children",
               return_value=[(90, "VILLA_VERDE", False), (91, "SEND_CUL", False)]):
        result = run(campaign_id=68, execute=False, max_children=12,
                     delay_seconds=0, session=session,
                     capture=lambda **kwargs: pytest.fail("provider called"))
    assert result["pending"] == 2
    assert result["attempted"] == 0
    session.rollback.assert_not_called()
    session.commit.assert_not_called()


def test_execute_gets_each_missing_child_once_and_isolates_failures():
    session = MagicMock()
    calls = []

    def capture(**kwargs):
        calls.append(kwargs["child_id"])
        if kwargs["child_id"] == 90:
            raise ValueError("provider failure")
        return {"created": True}

    with patch("scripts.marketing.capture_campaign_v2_stats.candidate_children",
               return_value=[(90, "VILLA_VERDE", False),
                             (91, "SEND_CUL", False),
                             (92, "TEC_MXL", True)]):
        result = run(campaign_id=68, execute=True, max_children=12,
                     delay_seconds=0, session=session, capture=capture,
                     sleeper=lambda seconds: None)
    assert calls == [90, 91]
    assert result["created"] == 1
    assert result["failed"] == 1
    assert session.remove.call_count == 2
    session.rollback.assert_called_once()


def test_limit_blocks_provider_activity():
    session = MagicMock()
    with patch("scripts.marketing.capture_campaign_v2_stats.candidate_children",
               return_value=[(i, "X", False) for i in range(13)]):
        with pytest.raises(ValueError):
            run(campaign_id=68, execute=True, max_children=12,
                delay_seconds=0, session=session,
                capture=lambda **kwargs: pytest.fail("provider called"))
