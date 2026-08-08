from app.models.feedback import GestureFeedback


def test_feedback_timestamps_have_application_and_database_defaults():
    created = GestureFeedback.__table__.c.created_at
    updated = GestureFeedback.__table__.c.updated_at
    assert created.default is not None
    assert created.server_default is not None
    assert updated.default is not None
    assert updated.server_default is not None
