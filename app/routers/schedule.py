# File: /backend/app/routers/schedule.py
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..deps import get_db
from ..core.roles import require_role, get_current_user

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/global")
def global_schedule(start: date | None = None, end: date | None = None, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.MEMBER))):
    assignments = db.query(models.UserShift).join(models.Shift).join(models.User).all()
    data = []
    for a in assignments:
        data.append({
            "assignment_id": str(a.id),
            "user": {"id": str(a.user.id), "name": a.user.name},
            "shift": {
                "id": str(a.shift.id),
                "name": a.shift.name,
                "weekday": a.shift.weekday,
                "start_time": a.shift.start_time.isoformat(),
                "end_time": a.shift.end_time.isoformat(),
                "location": a.shift.location,
            },
            "valid_from": a.valid_from.isoformat(),
            "valid_to": a.valid_to.isoformat() if a.valid_to else None,
        })
    return {"assignments": data}


@router.get("/me", response_model=list[schemas.AssignmentOut])
def my_schedule(current=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.UserShift).filter(models.UserShift.user_id == current.id).all()


@router.post("/shifts", response_model=schemas.ShiftOut)
def create_shift(payload: schemas.ShiftCreate, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    shift = models.Shift(**payload.dict())
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.post("/assign", response_model=schemas.AssignmentOut)
def assign_shift(payload: schemas.AssignmentCreate, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    assignment = models.UserShift(**payload.dict())
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/assign/{assignment_id}")
def delete_assignment(assignment_id: str, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    assignment = db.query(models.UserShift).filter(models.UserShift.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()
    return {"detail": "deleted"}
