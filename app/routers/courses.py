"""User + Course + Module endpoints (standard envelope)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..protocol import ok
from ..services.course_service import CourseService

router = APIRouter(prefix="/api", tags=["courses"])


def _dump(schema_cls, obj):
    return schema_cls.model_validate(obj).model_dump(mode="json")


# ---- Users ----
@router.post("/users", status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    user = models.User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok(_dump(schemas.UserOut, user))


@router.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return ok(_dump(schemas.UserOut, user))


# ---- Courses ----
@router.post("/users/{user_id}/courses", status_code=201)
def create_course(user_id: int, payload: schemas.CourseCreate, db: Session = Depends(get_db)):
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    course = models.Course(user_id=user_id, **payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return ok(_dump(schemas.CourseOut, course))


@router.get("/users/{user_id}/courses")
def list_courses(user_id: int, include_counts: bool = False, db: Session = Depends(get_db)):
    courses = db.scalars(
        select(models.Course).where(models.Course.user_id == user_id)
    ).all()
    if not include_counts:
        return ok([_dump(schemas.CourseOut, c) for c in courses])
    counts = CourseService.course_counts(db, [c.id for c in courses])
    return ok([
        {
            **_dump(schemas.CourseOut, c),
            "module_count": counts.get(c.id, {}).get("module_count", 0),
            "topic_count": counts.get(c.id, {}).get("topic_count", 0),
        }
        for c in courses
    ])


@router.patch("/courses/{course_id}")
def update_course(course_id: int, payload: schemas.CourseUpdate, db: Session = Depends(get_db)):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(course, k, v)
    db.commit()
    db.refresh(course)
    return ok(_dump(schemas.CourseOut, course))


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    CourseService.delete_course(db, course_id)
    return ok({"deleted": True, "id": course_id})


# ---- Modules ----
@router.post("/courses/{course_id}/modules", status_code=201)
def create_module(course_id: int, payload: schemas.ModuleCreate, db: Session = Depends(get_db)):
    if not db.get(models.Course, course_id):
        raise HTTPException(404, "Course not found")
    module = models.Module(course_id=course_id, **payload.model_dump())
    db.add(module)
    db.commit()
    db.refresh(module)
    return ok(_dump(schemas.ModuleOut, module))


@router.get("/courses/{course_id}/modules")
def list_modules(course_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(models.Module)
        .where(models.Module.course_id == course_id)
        .order_by(models.Module.order_index)
    ).all()
    return ok([_dump(schemas.ModuleOut, m) for m in rows])


@router.patch("/modules/{module_id}")
def update_module(module_id: int, payload: schemas.ModuleUpdate, db: Session = Depends(get_db)):
    module = CourseService.require_module(db, module_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(module, k, v)
    db.commit()
    db.refresh(module)
    return ok(_dump(schemas.ModuleOut, module))


@router.delete("/modules/{module_id}")
def delete_module(module_id: int, db: Session = Depends(get_db)):
    CourseService.delete_module(db, module_id)
    return ok({"deleted": True, "id": module_id})
