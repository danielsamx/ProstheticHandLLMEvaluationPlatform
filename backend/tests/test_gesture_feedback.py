import pytest
from pydantic import ValidationError

from app.schemas.feedback import GestureFeedbackIn


def test_negative_feedback_requires_actionable_evidence():
    with pytest.raises(ValidationError):
        GestureFeedbackIn(is_correct=False)


def test_feedback_retry_is_bounded():
    with pytest.raises(ValidationError):
        GestureFeedbackIn(is_correct=False, notes="Index finger remained open", max_attempts=10)


def test_positive_feedback_needs_no_correction_text():
    assert GestureFeedbackIn(is_correct=True).is_correct
