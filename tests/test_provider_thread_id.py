"""Provider-thread identity must survive local row-ID reuse."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.agent.tutor import _thread_id


def test_new_conversation_gets_an_opaque_unique_provider_thread_id():
    db = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    models.Base.metadata.create_all(db.bind)
    db.add(models.User(id=1, name="Student", email="student@example.test"))
    db.commit()

    first = models.Conversation(user_id=1, title="First")
    second = models.Conversation(user_id=1, title="Second")
    db.add_all([first, second])
    db.commit()

    assert first.provider_thread_id != second.provider_thread_id
    assert _thread_id(first) != _thread_id(second)
    assert _thread_id(first).startswith("tutor_")


def test_provider_thread_id_does_not_depend_on_reused_local_row_id():
    db = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    models.Base.metadata.create_all(db.bind)
    db.add(models.User(id=1, name="Student", email="student@example.test"))
    db.commit()

    old = models.Conversation(user_id=1, title="Old")
    db.add(old)
    db.commit()
    old_thread = _thread_id(old)
    db.delete(old)
    db.commit()

    replacement = models.Conversation(user_id=1, title="Replacement")
    db.add(replacement)
    db.commit()

    assert _thread_id(replacement) != old_thread
