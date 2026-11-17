from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan
from app.services.errors import Conflict, NotFound


def create_plan(db: Session, account_id: str, code: str, name: str, price_cents: int, interval_days: int, trial_days: int) -> Plan:
    if db.scalar(select(Plan.id).where(Plan.account_id == account_id, Plan.code == code)):
        raise Conflict(f"plan {code!r} exists")
    plan = Plan(account_id=account_id, code=code, name=name, price_cents=price_cents, interval_days=interval_days, trial_days=trial_days)
    db.add(plan)
    db.commit()
    return plan


def get_plan(db: Session, account_id: str, code: str) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.account_id == account_id, Plan.code == code))
    if plan is None:
        raise NotFound(f"plan {code}")
    return plan
