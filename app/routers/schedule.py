# File: /backend/app/routers/schedule.py
from datetime import date, time as time_obj
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..deps import get_db
from ..core.roles import require_role, get_current_user
from ..core.audit import record_log
from ..services.schedule_calc import week_events

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/global")
def global_schedule(start: date | None = None, end: date | None = None, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.MEMBER))):
    query = db.query(models.UserShift).join(models.Shift).join(models.User)
    if current.role == models.UserRole.MEMBER:
        query = query.filter(models.UserShift.user_id == current.id)
    assignments = query.all()
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


@router.get("/shifts", response_model=list[schemas.ShiftOut])
def list_shifts(db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.MEMBER))):
    return db.query(models.Shift).order_by(models.Shift.weekday, models.Shift.start_time).all()


def _ensure_slot(db: Session, slot: schemas.ShiftSlot) -> models.Shift:
    existing = db.query(models.Shift).filter(
        models.Shift.weekday == slot.weekday,
        models.Shift.start_time == slot.start_time,
        models.Shift.end_time == slot.end_time,
    ).first()
    if existing:
        return existing
    name = slot.name or f"Slot {slot.weekday} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
    shift = models.Shift(
        name=name,
        weekday=slot.weekday,
        start_time=slot.start_time,
        end_time=slot.end_time,
        location=slot.location,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.post("/slots/ensure", response_model=schemas.ShiftOut)
def ensure_slot(slot: schemas.ShiftSlot, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.MEMBER))):
    return _ensure_slot(db, slot)


@router.get("/weekly_view", response_model=list[schemas.ScheduleEvent])
def weekly_view(start: date, user_id: str | None = None, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.MEMBER))):
    # 멤버가 다른 사용자를 조회하지 않도록 제한
    if current.role == models.UserRole.MEMBER and user_id and user_id != str(current.id):
        raise HTTPException(status_code=403, detail="다른 사용자의 일정은 조회할 수 없습니다")
    target_user = user_id if user_id else None
    return week_events(db, start, target_user)


@router.post("/slots/assign", response_model=schemas.AssignmentOut)
def assign_slot(payload: schemas.SlotAssign, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    start_hour = max(0, min(23, payload.start_hour))
    end_hour = payload.end_hour if payload.end_hour is not None else min(24, start_hour + 1)
    if end_hour <= start_hour:
        raise HTTPException(status_code=400, detail="시간 범위가 올바르지 않습니다. 시작보다 늦은 종료 시각을 선택하세요.")
    if payload.valid_to and payload.valid_to < payload.valid_from:
        raise HTTPException(status_code=400, detail="종료일은 시작일 이후여야 합니다")

    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="대상 사용자를 찾을 수 없습니다")
    if user.role != models.UserRole.MEMBER:
        raise HTTPException(status_code=400, detail="마스터/운영자는 근무 배정 대상에서 제외됩니다")

    slot = schemas.ShiftSlot(
        weekday=payload.weekday,
        start_time=time_obj(hour=start_hour),
        end_time=time_obj(hour=end_hour),
        location=payload.location,
    )
    shift = _ensure_slot(db, slot)

    existing = (
        db.query(models.UserShift)
        .filter(
            models.UserShift.user_id == payload.user_id,
            models.UserShift.shift_id == shift.id,
            models.UserShift.valid_from <= payload.valid_from,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="이미 동일한 시간 슬롯이 이 사용자에게 배정되어 있습니다")

    assignment = models.UserShift(
        user_id=payload.user_id,
        shift_id=shift.id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    record_log(
        db,
        actor_id=str(current.id),
        action="ASSIGN_SLOT",
        target_user_id=str(payload.user_id),
        details={
            "weekday": payload.weekday,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "valid_from": payload.valid_from.isoformat(),
            "valid_to": payload.valid_to.isoformat() if payload.valid_to else None,
        },
    )
    db.commit()
    return assignment


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
