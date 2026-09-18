"""Relationship/ownership checks at user-scoped write boundaries."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.services.course_service import CourseService


def _db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        models.User(id=1, name="One", email="one@example.test"),
        models.User(id=2, name="Two", email="two@example.test"),
        models.Course(id=10, user_id=2, name="Private", code="P"),
        models.Module(id=20, course_id=10, name="Module"),
        models.Topic(id=30, module_id=20, name="Topic"),
    ])
    db.commit()
    return db


@pytest.mark.parametrize("method,object_id", [
    ("require_user_course", 10),
    ("require_user_module", 20),
    ("require_user_topic", 30),
])
def test_cross_user_hierarchy_looks_not_found(method, object_id):
    with pytest.raises(HTTPException) as error:
        getattr(CourseService, method)(_db(), 1, object_id)
    assert error.value.status_code == 404
