# File: /backend/app/routers/visitors.py
from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_db
from ..core.roles import get_current_user

router = APIRouter(prefix="/visitors", tags=["visitors"])


PERIOD_DEFAULTS = {
    models.VisitorPeriodType.SEMESTER_1: "1학기",
    models.VisitorPeriodType.SEMESTER_2: "2학기",
    models.VisitorPeriodType.SUMMER_BREAK: "여름방학",
    models.VisitorPeriodType.WINTER_BREAK: "겨울방학",
}


def _default_year_dates(academic_year: int) -> tuple[date, date]:
    start_date = date(academic_year, 3, 1)
    end_day = calendar.monthrange(academic_year + 1, 2)[1]
    end_date = date(academic_year + 1, 2, end_day)
    return start_date, end_date


def _get_year(db: Session, year_id) -> models.VisitorSchoolYear:
    year = db.query(models.VisitorSchoolYear).filter(models.VisitorSchoolYear.id == year_id).first()
    if not year:
        raise HTTPException(status_code=404, detail="학년도 정보를 찾을 수 없습니다.")
    return year


def _ensure_within_year(year: models.VisitorSchoolYear, visit_date: date) -> None:
    if visit_date < year.start_date or visit_date > year.end_date:
        raise HTTPException(status_code=400, detail="학년도 기간 밖의 날짜입니다.")


def _recalculate_entries(db: Session, year: models.VisitorSchoolYear) -> None:
    entries = (
        db.query(models.VisitorDailyCount)
        .filter(models.VisitorDailyCount.school_year_id == year.id)
        .order_by(models.VisitorDailyCount.visit_date.asc())
        .all()
    )
    if not entries:
        return

    anchor_index = next(
        (index for index, entry in enumerate(entries) if entry.baseline_total is not None),
        0,
    )

    def apply_entry(entry: models.VisitorDailyCount, previous_total: int) -> None:
        has_counts = entry.count1 is not None or entry.count2 is not None
        total = (entry.count1 or 0) + (entry.count2 or 0) if has_counts else None
        if total is None:
            if entry.daily_override is not None:
                total = previous_total + entry.daily_override
            else:
                total = previous_total
        entry.total_count = total
        entry.previous_total = previous_total
        if entry.daily_override is not None:
            entry.daily_visitors = entry.daily_override
        elif has_counts:
            entry.daily_visitors = entry.total_count - entry.previous_total
        else:
            entry.daily_visitors = 0

    anchor_entry = entries[anchor_index]
    anchor_prev_total = anchor_entry.baseline_total
    if anchor_prev_total is None:
        anchor_prev_total = year.initial_total or 0
    apply_entry(anchor_entry, anchor_prev_total)

    for index in range(anchor_index + 1, len(entries)):
        entry = entries[index]
        prev_total = entries[index - 1].total_count
        if entry.baseline_total is not None:
            prev_total = entry.baseline_total
        apply_entry(entry, prev_total)

    for index in range(anchor_index - 1, -1, -1):
        entry = entries[index]
        next_entry = entries[index + 1]
        has_counts = entry.count1 is not None or entry.count2 is not None
        if has_counts:
            total = (entry.count1 or 0) + (entry.count2 or 0)
        elif next_entry.previous_total is not None:
            total = next_entry.previous_total
        else:
            total = 0
        entry.total_count = total
        if entry.daily_override is not None:
            entry.previous_total = total - entry.daily_override
            entry.daily_visitors = entry.daily_override
        else:
            entry.previous_total = total
            entry.daily_visitors = 0
    db.flush()


def _month_iter(start_date: date, end_date: date):
    current = date(start_date.year, start_date.month, 1)
    end_marker = date(end_date.year, end_date.month, 1)
    while current <= end_marker:
        yield current.year, current.month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _build_summary(year: models.VisitorSchoolYear, entries: list[models.VisitorDailyCount], periods: list[models.VisitorPeriod]) -> schemas.VisitorSummary:
    total_visitors = sum(entry.daily_visitors for entry in entries)
    open_days = len(entries)

    monthly_stats: list[schemas.VisitorMonthlyStat] = []
    entries_by_month: dict[tuple[int, int], list[models.VisitorDailyCount]] = {}
    for entry in entries:
        key = (entry.visit_date.year, entry.visit_date.month)
        entries_by_month.setdefault(key, []).append(entry)
    for year_value, month_value in _month_iter(year.start_date, year.end_date):
        month_entries = entries_by_month.get((year_value, month_value), [])
        label = f"{year_value}년 {month_value}월"
        monthly_stats.append(
            schemas.VisitorMonthlyStat(
                year=year_value,
                month=month_value,
                label=label,
                open_days=len(month_entries),
                total_visitors=sum(item.daily_visitors for item in month_entries),
            )
        )

    period_stats: list[schemas.VisitorPeriodStat] = []
    for period in periods:
        if not period.start_date or not period.end_date:
            period_stats.append(
                schemas.VisitorPeriodStat(
                    period_type=period.period_type,
                    name=period.name,
                    start_date=period.start_date,
                    end_date=period.end_date,
                    open_days=0,
                    total_visitors=0,
                )
            )
            continue
        period_entries = [
            entry
            for entry in entries
            if period.start_date <= entry.visit_date <= period.end_date
        ]
        period_stats.append(
            schemas.VisitorPeriodStat(
                period_type=period.period_type,
                name=period.name,
                start_date=period.start_date,
                end_date=period.end_date,
                open_days=len(period_entries),
                total_visitors=sum(item.daily_visitors for item in period_entries),
            )
        )

    return schemas.VisitorSummary(
        total_visitors=total_visitors,
        open_days=open_days,
        monthly=monthly_stats,
        periods=period_stats,
    )


@router.get("/years", response_model=list[schemas.VisitorYearOut])
def list_years(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return db.query(models.VisitorSchoolYear).order_by(models.VisitorSchoolYear.academic_year.desc()).all()


@router.post("/years", response_model=schemas.VisitorYearOut, status_code=status.HTTP_201_CREATED)
def create_year(payload: schemas.VisitorYearCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if db.query(models.VisitorSchoolYear).filter(models.VisitorSchoolYear.academic_year == payload.academic_year).first():
        raise HTTPException(status_code=400, detail="이미 등록된 학년도입니다.")
    start_date, end_date = _default_year_dates(payload.academic_year)
    if payload.start_date:
        start_date = payload.start_date
    if payload.end_date:
        end_date = payload.end_date
    label = payload.label or f"{payload.academic_year}학년도 참고자료실 출입자 통계"
    year = models.VisitorSchoolYear(
        academic_year=payload.academic_year,
        label=label,
        start_date=start_date,
        end_date=end_date,
        initial_total=payload.initial_total or 0,
    )
    db.add(year)
    db.flush()
    for period_type, default_name in PERIOD_DEFAULTS.items():
        db.add(
            models.VisitorPeriod(
                school_year_id=year.id,
                period_type=period_type,
                name=default_name,
            )
        )
    db.commit()
    db.refresh(year)
    return year


@router.get("/years/{year_id}", response_model=schemas.VisitorYearDetail)
def get_year_detail(year_id, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    periods = (
        db.query(models.VisitorPeriod)
        .filter(models.VisitorPeriod.school_year_id == year.id)
        .order_by(models.VisitorPeriod.period_type.asc())
        .all()
    )
    entries = (
        db.query(models.VisitorDailyCount)
        .filter(models.VisitorDailyCount.school_year_id == year.id)
        .order_by(models.VisitorDailyCount.visit_date.desc())
        .all()
    )
    users = {u.id: u for u in db.query(models.User).all()}
    entry_out = []
    for entry in entries:
        entry_out.append(
            schemas.VisitorEntryOut(
                id=entry.id,
                school_year_id=entry.school_year_id,
                visit_date=entry.visit_date,
                count1=entry.count1,
                count2=entry.count2,
                baseline_total=entry.baseline_total,
                daily_override=entry.daily_override,
                total_count=entry.total_count,
                previous_total=entry.previous_total,
                daily_visitors=entry.daily_visitors,
                created_by=entry.created_by,
                updated_by=entry.updated_by,
                created_by_name=users.get(entry.created_by).name if entry.created_by in users else None,
                updated_by_name=users.get(entry.updated_by).name if entry.updated_by in users else None,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
        )
    summary = _build_summary(year, list(reversed(entries)), periods)
    return schemas.VisitorYearDetail(
        year=schemas.VisitorYearOut.model_validate(year),
        periods=[schemas.VisitorPeriodOut.model_validate(period) for period in periods],
        entries=entry_out,
        summary=summary,
    )


@router.put("/years/{year_id}", response_model=schemas.VisitorYearOut)
def update_year(year_id, payload: schemas.VisitorYearUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    if payload.label is not None:
        year.label = payload.label
    if payload.start_date is not None:
        year.start_date = payload.start_date
    if payload.end_date is not None:
        year.end_date = payload.end_date
    if payload.initial_total is not None:
        year.initial_total = payload.initial_total
        _recalculate_entries(db, year)
    db.commit()
    db.refresh(year)
    return year


@router.put("/years/{year_id}/periods", response_model=list[schemas.VisitorPeriodOut])
def upsert_periods(year_id, payload: list[schemas.VisitorPeriodUpsert], db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    existing = {
        period.period_type: period
        for period in db.query(models.VisitorPeriod)
        .filter(models.VisitorPeriod.school_year_id == year.id)
        .all()
    }
    for item in payload:
        period = existing.get(item.period_type)
        if period:
            period.name = item.name
            period.start_date = item.start_date
            period.end_date = item.end_date
        else:
            db.add(
                models.VisitorPeriod(
                    school_year_id=year.id,
                    period_type=item.period_type,
                    name=item.name,
                    start_date=item.start_date,
                    end_date=item.end_date,
                )
            )
    db.commit()
    periods = (
        db.query(models.VisitorPeriod)
        .filter(models.VisitorPeriod.school_year_id == year.id)
        .order_by(models.VisitorPeriod.period_type.asc())
        .all()
    )
    return [schemas.VisitorPeriodOut.model_validate(period) for period in periods]


@router.post("/years/{year_id}/entries", response_model=schemas.VisitorEntryOut)
def upsert_entry(year_id, payload: schemas.VisitorEntryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    _ensure_within_year(year, payload.visit_date)
    entry = (
        db.query(models.VisitorDailyCount)
        .filter(
            models.VisitorDailyCount.school_year_id == year.id,
            models.VisitorDailyCount.visit_date == payload.visit_date,
        )
        .first()
    )
    if entry:
        entry.count1 = payload.count1
        entry.count2 = payload.count2
        entry.baseline_total = payload.baseline_total
        entry.daily_override = payload.daily_override
        entry.updated_by = current_user.id
    else:
        entry = models.VisitorDailyCount(
            school_year_id=year.id,
            visit_date=payload.visit_date,
            count1=payload.count1,
            count2=payload.count2,
            baseline_total=payload.baseline_total,
            daily_override=payload.daily_override,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(entry)
    _recalculate_entries(db, year)
    db.commit()
    db.refresh(entry)
    users = {u.id: u for u in db.query(models.User).all()}
    return schemas.VisitorEntryOut(
        id=entry.id,
        school_year_id=entry.school_year_id,
        visit_date=entry.visit_date,
        count1=entry.count1,
        count2=entry.count2,
        baseline_total=entry.baseline_total,
        daily_override=entry.daily_override,
        total_count=entry.total_count,
        previous_total=entry.previous_total,
        daily_visitors=entry.daily_visitors,
        created_by=entry.created_by,
        updated_by=entry.updated_by,
        created_by_name=users.get(entry.created_by).name if entry.created_by in users else None,
        updated_by_name=users.get(entry.updated_by).name if entry.updated_by in users else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.delete("/years/{year_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(year_id, entry_id, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    entry = (
        db.query(models.VisitorDailyCount)
        .filter(models.VisitorDailyCount.school_year_id == year.id, models.VisitorDailyCount.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    db.delete(entry)
    _recalculate_entries(db, year)
    db.commit()
    return None
