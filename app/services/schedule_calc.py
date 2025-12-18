from datetime import date, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from .. import models, schemas


def _valid_for_date(assignment: models.UserShift, target: date) -> bool:
    if assignment.valid_from > target:
        return False
    if assignment.valid_to and assignment.valid_to < target:
        return False
    return True


def week_events(db: Session, start: date, user_filter: str | None = None) -> list[schemas.ScheduleEvent]:
    """기존 배정과 승인된 요청(결근/추가)을 합친 주간 이벤트를 계산."""
    end = start + timedelta(days=6)
    assignments = db.query(models.UserShift).join(models.Shift).join(models.User)
    if user_filter:
        assignments = assignments.filter(models.UserShift.user_id == user_filter)
    assignments = assignments.all()

    requests = db.query(models.ShiftRequest).filter(
        models.ShiftRequest.status == models.RequestStatus.APPROVED,
        models.ShiftRequest.target_date >= start,
        models.ShiftRequest.target_date <= end,
    )
    if user_filter:
        requests = requests.filter(models.ShiftRequest.user_id == user_filter)
    requests = requests.all()

    users = {u.id: u for u in db.query(models.User).all()}
    shifts = {s.id: s for s in db.query(models.Shift).all()}

    base_events: list[schemas.ScheduleEvent] = []
    base_keys = set()

    for offset in range(7):
        current_date = start + timedelta(days=offset)
        weekday = current_date.weekday()
        for a in assignments:
            if not _valid_for_date(a, current_date):
                continue
            if a.shift.weekday != weekday:
                continue
            key = (str(a.user_id), current_date, str(a.shift_id))
            base_keys.add(key)
            base_events.append(
                schemas.ScheduleEvent(
                    user_id=a.user_id,
                    user_name=a.user.name,
                    role=a.user.role,
                    date=current_date,
                    start_time=a.shift.start_time,
                    end_time=a.shift.end_time,
                    shift_id=a.shift_id,
                    shift_name=a.shift.name,
                    location=a.shift.location,
                    source="BASE",
                )
            )

    # remove absences
    for req in requests:
        if req.type == models.RequestType.ABSENCE:
            base_keys.discard((str(req.user_id), req.target_date, str(req.target_shift_id)))

    filtered_events = [ev for ev in base_events if (str(ev.user_id), ev.date, str(ev.shift_id)) in base_keys]

    # extras add
    extras: list[schemas.ScheduleEvent] = []
    for req in requests:
        if req.type != models.RequestType.EXTRA:
            continue
        shift = shifts.get(req.target_shift_id)
        user = users.get(req.user_id)
        if not shift or not user:
            continue
        extras.append(
            schemas.ScheduleEvent(
                user_id=user.id,
                user_name=user.name,
                role=user.role,
                date=req.target_date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                shift_id=shift.id,
                shift_name=shift.name,
                location=shift.location,
                source="EXTRA",
            )
        )

    return filtered_events + extras
