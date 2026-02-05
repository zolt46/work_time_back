# File: /backend/app/routers/visitors.py
from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, aliased

from .. import models, schemas
from ..deps import get_db
from ..core.roles import get_current_user, require_role

router = APIRouter(prefix="/visitors", tags=["visitors"])


PERIOD_DEFAULTS = {
    models.VisitorPeriodType.SEMESTER_1: "1학기",
    models.VisitorPeriodType.SEMESTER_2: "2학기",
    models.VisitorPeriodType.SUMMER_BREAK: "여름방학",
    models.VisitorPeriodType.WINTER_BREAK: "겨울방학",
}

MAX_DAILY_VISITORS = 1_000_000

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


def _ensure_non_negative(label: str, value: int | None, max_value: int) -> None:
    if value is None:
        return
    if value < 0:
        raise HTTPException(status_code=400, detail=f"{label}은(는) 0 이상이어야 합니다.")
    if value > max_value:
        raise HTTPException(status_code=400, detail=f"{label}은(는) {max_value:,} 이하만 입력할 수 있습니다.")


def _validate_daily_visitors(value: int | None) -> None:
    if value is None:
        raise HTTPException(status_code=400, detail="일일 방문자 수를 입력하세요.")
    _ensure_non_negative("일일 방문자 수", value, MAX_DAILY_VISITORS)


def _get_running_total(db: Session, year: models.VisitorSchoolYear) -> models.VisitorRunningTotal:
    running = (
        db.query(models.VisitorRunningTotal)
        .filter(models.VisitorRunningTotal.school_year_id == year.id)
        .first()
    )
    if not running:
        running = models.VisitorRunningTotal(school_year_id=year.id)
        db.add(running)
        db.flush()
    return running


def _apply_entry_delta(
    db: Session,
    year: models.VisitorSchoolYear,
    visit_date: date,
    delta_visitors: int,
    delta_days: int,
) -> None:
    year_stat = (
        db.query(models.VisitorYearStat)
        .filter(models.VisitorYearStat.school_year_id == year.id)
        .first()
    )
    if not year_stat:
        year_stat = models.VisitorYearStat(school_year_id=year.id)
        db.add(year_stat)
        db.flush()
    year_stat.total_visitors = max(0, (year_stat.total_visitors or 0) + delta_visitors)
    year_stat.open_days = max(0, (year_stat.open_days or 0) + delta_days)

    monthly_stat = (
        db.query(models.VisitorMonthlyStat)
        .filter(
            models.VisitorMonthlyStat.school_year_id == year.id,
            models.VisitorMonthlyStat.year == visit_date.year,
            models.VisitorMonthlyStat.month == visit_date.month,
        )
        .first()
    )
    if not monthly_stat:
        monthly_stat = models.VisitorMonthlyStat(
            school_year_id=year.id,
            year=visit_date.year,
            month=visit_date.month,
        )
        db.add(monthly_stat)
        db.flush()
    monthly_stat.total_visitors = max(0, (monthly_stat.total_visitors or 0) + delta_visitors)
    monthly_stat.open_days = max(0, (monthly_stat.open_days or 0) + delta_days)

    period = (
        db.query(models.VisitorPeriod)
        .filter(
            models.VisitorPeriod.school_year_id == year.id,
            models.VisitorPeriod.start_date.isnot(None),
            models.VisitorPeriod.end_date.isnot(None),
            models.VisitorPeriod.start_date <= visit_date,
            models.VisitorPeriod.end_date >= visit_date,
        )
        .first()
    )
    if period:
        period_stat = (
            db.query(models.VisitorPeriodStat)
            .filter(
                models.VisitorPeriodStat.school_year_id == year.id,
                models.VisitorPeriodStat.period_id == period.id,
            )
            .first()
        )
        if not period_stat:
            period_stat = models.VisitorPeriodStat(
                school_year_id=year.id,
                period_id=period.id,
            )
            db.add(period_stat)
            db.flush()
        period_stat.total_visitors = max(0, (period_stat.total_visitors or 0) + delta_visitors)
        period_stat.open_days = max(0, (period_stat.open_days or 0) + delta_days)


def _rebuild_period_stats(db: Session, year: models.VisitorSchoolYear) -> None:
    db.query(models.VisitorPeriodStat).filter(models.VisitorPeriodStat.school_year_id == year.id).delete()
    periods = (
        db.query(models.VisitorPeriod)
        .filter(models.VisitorPeriod.school_year_id == year.id)
        .all()
    )
    for period in periods:
        if not period.start_date or not period.end_date:
            continue
        entries = (
            db.query(models.VisitorDailyCount)
            .filter(
                models.VisitorDailyCount.school_year_id == year.id,
                models.VisitorDailyCount.visit_date >= period.start_date,
                models.VisitorDailyCount.visit_date <= period.end_date,
            )
            .all()
        )
        db.add(
            models.VisitorPeriodStat(
                school_year_id=year.id,
                period_id=period.id,
                total_visitors=sum(entry.daily_visitors for entry in entries),
                open_days=len(entries),
            )
        )


def _ensure_monthly_stats(db: Session, year: models.VisitorSchoolYear, entries: list[models.VisitorDailyCount]) -> list[models.VisitorMonthlyStat]:
    existing_stats = (
        db.query(models.VisitorMonthlyStat)
        .filter(models.VisitorMonthlyStat.school_year_id == year.id)
        .all()
    )
    existing_keys = {(stat.year, stat.month) for stat in existing_stats}
    grouped: dict[tuple[int, int], list[models.VisitorDailyCount]] = {}
    for entry in entries:
        key = (entry.visit_date.year, entry.visit_date.month)
        grouped.setdefault(key, []).append(entry)
    for (year_value, month_value), items in grouped.items():
        if (year_value, month_value) in existing_keys:
            continue
        db.add(
            models.VisitorMonthlyStat(
                school_year_id=year.id,
                year=year_value,
                month=month_value,
                total_visitors=sum(item.daily_visitors for item in items),
                open_days=len(items),
            )
        )
    return existing_stats


def _ensure_year_stat(
    db: Session,
    year: models.VisitorSchoolYear,
    entries: list[models.VisitorDailyCount],
    monthly_stats: list[models.VisitorMonthlyStat],
) -> models.VisitorYearStat:
    year_stat = (
        db.query(models.VisitorYearStat)
        .filter(models.VisitorYearStat.school_year_id == year.id)
        .first()
    )
    if year_stat:
        return year_stat
    if monthly_stats:
        total_visitors = sum(stat.total_visitors for stat in monthly_stats)
        open_days = sum(stat.open_days for stat in monthly_stats)
    else:
        total_visitors = sum(entry.daily_visitors for entry in entries)
        open_days = len(entries)
    year_stat = models.VisitorYearStat(
        school_year_id=year.id,
        total_visitors=total_visitors,
        open_days=open_days,
    )
    db.add(year_stat)
    return year_stat


def _ensure_period_stats(
    db: Session,
    year: models.VisitorSchoolYear,
    periods: list[models.VisitorPeriod],
    entries: list[models.VisitorDailyCount],
) -> None:
    existing_stats = (
        db.query(models.VisitorPeriodStat)
        .filter(models.VisitorPeriodStat.school_year_id == year.id)
        .all()
    )
    existing_period_ids = {stat.period_id for stat in existing_stats}
    for period in periods:
        if period.id in existing_period_ids:
            continue
        if not period.start_date or not period.end_date:
            continue
        period_entries = [
            entry
            for entry in entries
            if period.start_date <= entry.visit_date <= period.end_date
        ]
        db.add(
            models.VisitorPeriodStat(
                school_year_id=year.id,
                period_id=period.id,
                total_visitors=sum(entry.daily_visitors for entry in period_entries),
                open_days=len(period_entries),
            )
        )


def _month_iter(start_date: date, end_date: date):
    current = date(start_date.year, start_date.month, 1)
    end_marker = date(end_date.year, end_date.month, 1)
    while current <= end_marker:
        yield current.year, current.month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _build_summary(
    year: models.VisitorSchoolYear,
    periods: list[models.VisitorPeriod],
    monthly_stats: list[models.VisitorMonthlyStat],
    period_stats: list[models.VisitorPeriodStat],
    year_stat: models.VisitorYearStat | None,
) -> schemas.VisitorSummary:
    total_visitors = year_stat.total_visitors if year_stat else 0
    open_days = year_stat.open_days if year_stat else 0

    monthly_map = {(stat.year, stat.month): stat for stat in monthly_stats}
    monthly_out: list[schemas.VisitorMonthlyStat] = []
    for year_value, month_value in _month_iter(year.start_date, year.end_date):
        stat = monthly_map.get((year_value, month_value))
        label = f"{year_value}년 {month_value}월"
        monthly_out.append(
            schemas.VisitorMonthlyStat(
                year=year_value,
                month=month_value,
                label=label,
                open_days=stat.open_days if stat else 0,
                total_visitors=stat.total_visitors if stat else 0,
            )
        )

    period_stat_map = {stat.period_id: stat for stat in period_stats}
    period_out: list[schemas.VisitorPeriodStat] = []
    for period in periods:
        stat = period_stat_map.get(period.id)
        period_out.append(
            schemas.VisitorPeriodStat(
                period_type=period.period_type,
                name=period.name,
                start_date=period.start_date,
                end_date=period.end_date,
                open_days=stat.open_days if stat else 0,
                total_visitors=stat.total_visitors if stat else 0,
            )
        )

    return schemas.VisitorSummary(
        total_visitors=total_visitors,
        open_days=open_days,
        monthly=monthly_out,
        periods=period_out,
    )


@router.get("/years", response_model=list[schemas.VisitorYearOut])
def list_years(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return db.query(models.VisitorSchoolYear).order_by(models.VisitorSchoolYear.academic_year.desc()).all()


@router.post("/years", response_model=schemas.VisitorYearOut, status_code=status.HTTP_201_CREATED)
def create_year(payload: schemas.VisitorYearCreate, db: Session = Depends(get_db), current_user=Depends(require_role(models.UserRole.OPERATOR))):
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
    db.add(models.VisitorRunningTotal(school_year_id=year.id))
    db.add(models.VisitorYearStat(school_year_id=year.id))
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
    creator = aliased(models.User)
    updater = aliased(models.User)
    entries = (
        db.query(
            models.VisitorDailyCount,
            creator.name.label("creator_name"),
            updater.name.label("updater_name"),
        )
        .outerjoin(creator, creator.id == models.VisitorDailyCount.created_by)
        .outerjoin(updater, updater.id == models.VisitorDailyCount.updated_by)
        .filter(models.VisitorDailyCount.school_year_id == year.id)
        .order_by(models.VisitorDailyCount.visit_date.desc())
        .all()
    )
    entry_records = [row[0] for row in entries]
    monthly_stats = _ensure_monthly_stats(db, year, entry_records)
    year_stat = _ensure_year_stat(db, year, entry_records, monthly_stats)
    _ensure_period_stats(db, year, periods, entry_records)
    db.flush()
    period_stats = (
        db.query(models.VisitorPeriodStat)
        .filter(models.VisitorPeriodStat.school_year_id == year.id)
        .all()
    )
    entry_out = []
    for entry, creator_name, updater_name in entries:
        entry_out.append(
            schemas.VisitorEntryOut(
                id=entry.id,
                school_year_id=entry.school_year_id,
                visit_date=entry.visit_date,
                daily_visitors=entry.daily_visitors,
                created_by=entry.created_by,
                updated_by=entry.updated_by,
                created_by_name=creator_name,
                updated_by_name=updater_name,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
        )
    summary = _build_summary(year, periods, monthly_stats, period_stats, year_stat)
    return schemas.VisitorYearDetail(
        year=schemas.VisitorYearOut.model_validate(year),
        periods=[schemas.VisitorPeriodOut.model_validate(period) for period in periods],
        entries=entry_out,
        summary=summary,
    )


@router.put("/years/{year_id}", response_model=schemas.VisitorYearOut)
def update_year(year_id, payload: schemas.VisitorYearUpdate, db: Session = Depends(get_db), current_user=Depends(require_role(models.UserRole.OPERATOR))):
    year = _get_year(db, year_id)
    if payload.label is not None:
        year.label = payload.label
    if payload.start_date is not None:
        year.start_date = payload.start_date
    if payload.end_date is not None:
        year.end_date = payload.end_date
    db.commit()
    db.refresh(year)
    return year


@router.delete("/years/{year_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_year(year_id, db: Session = Depends(get_db), current_user=Depends(require_role(models.UserRole.OPERATOR))):
    year = _get_year(db, year_id)
    db.delete(year)
    db.commit()
    return None


@router.put("/years/{year_id}/periods", response_model=list[schemas.VisitorPeriodOut])
def upsert_periods(year_id, payload: list[schemas.VisitorPeriodUpsert], db: Session = Depends(get_db), current_user=Depends(require_role(models.UserRole.OPERATOR))):
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
    _rebuild_period_stats(db, year)
    db.commit()
    periods = (
        db.query(models.VisitorPeriod)
        .filter(models.VisitorPeriod.school_year_id == year.id)
        .order_by(models.VisitorPeriod.period_type.asc())
        .all()
    )
    return [schemas.VisitorPeriodOut.model_validate(period) for period in periods]


@router.post("/years/{year_id}/running-total/load", response_model=schemas.VisitorRunningTotalOut)
def load_running_total(year_id, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    running = _get_running_total(db, year)
    db.commit()
    db.refresh(running)
    return schemas.VisitorRunningTotalOut(
        previous_total=running.previous_total,
        current_total=running.current_total,
        running_date=running.running_date,
    )


@router.post("/years/{year_id}/entries", response_model=schemas.VisitorEntryOut)
def upsert_entry(year_id, payload: schemas.VisitorEntryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    year = _get_year(db, year_id)
    _ensure_within_year(year, payload.visit_date)
    today = date.today()
    if payload.visit_date != today:
        raise HTTPException(status_code=403, detail="일일 입력은 오늘 날짜만 가능합니다.")
    _validate_daily_visitors(payload.daily_visitors)
    if payload.previous_total is None:
        raise HTTPException(status_code=400, detail="전일 합산을 입력하거나 불러오세요.")
    entry = (
        db.query(models.VisitorDailyCount)
        .filter(
            models.VisitorDailyCount.school_year_id == year.id,
            models.VisitorDailyCount.visit_date == payload.visit_date,
        )
        .first()
    )
    if entry:
        is_operator = current_user.role in (models.UserRole.OPERATOR, models.UserRole.MASTER)
        if not is_operator and entry.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="본인이 입력한 기록만 수정할 수 있습니다.")
        delta_visitors = payload.daily_visitors - entry.daily_visitors
        entry.daily_visitors = payload.daily_visitors
        entry.updated_by = current_user.id
    else:
        delta_visitors = payload.daily_visitors
        entry = models.VisitorDailyCount(
            school_year_id=year.id,
            visit_date=payload.visit_date,
            daily_visitors=payload.daily_visitors,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(entry)
    running = _get_running_total(db, year)
    running.previous_total = payload.previous_total
    running.current_total = payload.previous_total
    running.running_date = today
    _apply_entry_delta(db, year, payload.visit_date, delta_visitors, 0 if entry.id else 1)
    db.commit()
    db.refresh(entry)
    users = {u.id: u for u in db.query(models.User).all()}
    return schemas.VisitorEntryOut(
        id=entry.id,
        school_year_id=entry.school_year_id,
        visit_date=entry.visit_date,
        daily_visitors=entry.daily_visitors,
        created_by=entry.created_by,
        updated_by=entry.updated_by,
        created_by_name=users.get(entry.created_by).name if entry.created_by in users else None,
        updated_by_name=users.get(entry.updated_by).name if entry.updated_by in users else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.delete("/years/{year_id}/entries", status_code=status.HTTP_204_NO_CONTENT)
def delete_entries(
    year_id,
    month: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(models.UserRole.OPERATOR)),
):
    year = _get_year(db, year_id)
    query = db.query(models.VisitorDailyCount).filter(models.VisitorDailyCount.school_year_id == year.id)
    if month:
        try:
            year_value, month_value = month.split("-")
            year_int = int(year_value)
            month_int = int(month_value)
            if not (1 <= month_int <= 12):
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="월 형식은 YYYY-MM 이어야 합니다.") from exc
        start_date = date(year_int, month_int, 1)
        end_day = calendar.monthrange(year_int, month_int)[1]
        end_date = date(year_int, month_int, end_day)
        query = query.filter(models.VisitorDailyCount.visit_date.between(start_date, end_date))
    entries = query.all()
    if entries:
        for entry in entries:
            _apply_entry_delta(db, year, entry.visit_date, -entry.daily_visitors, -1)
        for entry in entries:
            db.delete(entry)
    db.commit()
    return None


@router.post("/years/{year_id}/entries/bulk", response_model=list[schemas.VisitorEntryOut])
def bulk_upsert_entries(
    year_id,
    payload: schemas.VisitorBulkEntryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(models.UserRole.OPERATOR)),
):
    year = _get_year(db, year_id)
    if not payload.entries:
        raise HTTPException(status_code=400, detail="입력할 데이터가 없습니다.")

    seen_dates: set[date] = set()
    for item in payload.entries:
        _ensure_within_year(year, item.visit_date)
        if item.visit_date >= date.today():
            raise HTTPException(status_code=400, detail="오늘 날짜는 일일 입력에서만 가능합니다.")
        _validate_daily_visitors(item.daily_visitors)
        if item.visit_date in seen_dates:
            raise HTTPException(status_code=400, detail="중복된 날짜가 포함되어 있습니다.")
        seen_dates.add(item.visit_date)

    dates = list(seen_dates)
    existing_entries = (
        db.query(models.VisitorDailyCount)
        .filter(
            models.VisitorDailyCount.school_year_id == year.id,
            models.VisitorDailyCount.visit_date.in_(dates),
        )
        .all()
    )
    existing_map = {entry.visit_date: entry for entry in existing_entries}
    updated_entries: list[models.VisitorDailyCount] = []

    try:
        for item in payload.entries:
            entry = existing_map.get(item.visit_date)
            if entry:
                if entry.daily_visitors == item.daily_visitors:
                    continue
                delta_visitors = item.daily_visitors - entry.daily_visitors
                entry.daily_visitors = item.daily_visitors
                entry.updated_by = current_user.id
                _apply_entry_delta(db, year, item.visit_date, delta_visitors, 0)
            else:
                entry = models.VisitorDailyCount(
                    school_year_id=year.id,
                    visit_date=item.visit_date,
                    daily_visitors=item.daily_visitors,
                    created_by=current_user.id,
                    updated_by=current_user.id,
                )
                db.add(entry)
                _apply_entry_delta(db, year, item.visit_date, item.daily_visitors, 1)
            updated_entries.append(entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="일괄 저장 중 오류가 발생했습니다.") from exc

    users = {u.id: u for u in db.query(models.User).all()}
    results: list[schemas.VisitorEntryOut] = []
    for entry in updated_entries:
        db.refresh(entry)
        results.append(
            schemas.VisitorEntryOut(
                id=entry.id,
                school_year_id=entry.school_year_id,
                visit_date=entry.visit_date,
                daily_visitors=entry.daily_visitors,
                created_by=entry.created_by,
                updated_by=entry.updated_by,
                created_by_name=users.get(entry.created_by).name if entry.created_by in users else None,
                updated_by_name=users.get(entry.updated_by).name if entry.updated_by in users else None,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
        )
    return results


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
    is_operator = current_user.role in (models.UserRole.OPERATOR, models.UserRole.MASTER)
    today = date.today()
    if not is_operator:
        if entry.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="본인이 입력한 기록만 삭제할 수 있습니다.")
        if entry.visit_date != today:
            raise HTTPException(status_code=403, detail="오늘 날짜만 삭제할 수 있습니다.")
    db.delete(entry)
    _apply_entry_delta(db, year, entry.visit_date, -entry.daily_visitors, -1)
    if entry.visit_date == today:
        running = _get_running_total(db, year)
        if running.running_date == today:
            running.current_total = None
    db.commit()
    return None
