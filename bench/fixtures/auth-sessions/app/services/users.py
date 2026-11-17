from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.clock import utcnow
from app.config import settings
from app.models import AuditEvent, Invite, InviteStatus, Role, User, UserStatus
from app.security import hash_password, normalize_email, temporary_password, verify_password
from app.services import sessions
from app.services.errors import Conflict, InvalidCredentials, NotFound, PasswordPolicyError


def audit(db: DbSession, org_id: str, actor_id: int | None, action: str, target_id: int | None) -> None:
    db.add(AuditEvent(org_id=org_id, actor_id=actor_id, action=action, target_id=target_id))


def get_user_by_email(db: DbSession, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def get_org_user(db: DbSession, org_id: str, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.org_id != org_id:
        raise NotFound(f"user {user_id}")
    return user


def list_users(db: DbSession, org_id: str) -> list[User]:
    return list(db.scalars(select(User).where(User.org_id == org_id).order_by(User.email)))


def bootstrap_admin(db: DbSession, org_id: str, email: str, display_name: str, password: str) -> User:
    """Create an organisation's first admin (used by the setup script)."""
    check_password_policy(password, email)
    user = User(
        org_id=org_id,
        email=normalize_email(email),
        display_name=display_name,
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
        password_hash=hash_password(password),
        must_set_password=False,
    )
    db.add(user)
    db.commit()
    return user


def check_password_policy(password: str, email: str) -> None:
    if len(password) < settings.min_password_length:
        raise PasswordPolicyError(f"use at least {settings.min_password_length} characters")
    if normalize_email(email).split("@")[0] in password.lower():
        raise PasswordPolicyError("do not include your email name")


def create_invite(db: DbSession, admin: User, email: str, display_name: str, role: Role) -> tuple[Invite, str]:
    """Invite someone; returns the invite and the one-time password to hand them."""
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict(f"{email} already has an account")

    temp = temporary_password()
    user = User(
        org_id=admin.org_id,
        email=email,
        display_name=display_name,
        role=role,
        status=UserStatus.INVITED,
        password_hash=hash_password(temp),
        must_set_password=True,
    )
    db.add(user)
    db.flush()
    invite = Invite(
        org_id=admin.org_id,
        user_id=user.id,
        email=email,
        created_by=admin.id,
        expires_at=utcnow() + settings.invite_valid_for,
    )
    db.add(invite)
    audit(db, admin.org_id, admin.id, "invited", user.id)
    db.commit()
    return invite, temp


def revoke_invite(db: DbSession, admin: User, invite_id: int) -> Invite:
    invite = db.get(Invite, invite_id)
    if invite is None or invite.org_id != admin.org_id:
        raise NotFound(f"invite {invite_id}")
    result = db.execute(
        update(Invite)
        .where(Invite.id == invite.id, Invite.status == InviteStatus.PENDING)
        .values(status=InviteStatus.REVOKED, revoked_at=utcnow())
    )
    if result.rowcount == 0:
        db.rollback()
        raise Conflict(f"invite {invite_id} is {invite.status.value}")
    audit(db, admin.org_id, admin.id, "invite_revoked", invite.user_id)
    db.commit()
    db.refresh(invite)
    return invite


def admin_reset_password(db: DbSession, admin: User, user_id: int) -> str:
    """Give the user a one-time password; they must choose their own on next sign-in."""
    user = get_org_user(db, admin.org_id, user_id)
    if user.status != UserStatus.ACTIVE:
        raise Conflict(f"user {user_id} is {user.status.value}")

    temp = temporary_password()
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(password_hash=hash_password(temp), must_set_password=True, password_changed_at=utcnow())
    )
    sessions.revoke_all_for_user(db, user.id)
    audit(db, admin.org_id, admin.id, "password_reset", user.id)
    db.commit()
    return temp


def disable_user(db: DbSession, admin: User, user_id: int) -> User:
    user = get_org_user(db, admin.org_id, user_id)
    if user.id == admin.id:
        raise Conflict("you cannot disable your own account")
    db.execute(update(User).where(User.id == user.id).values(status=UserStatus.DISABLED))
    sessions.revoke_all_for_user(db, user.id)
    audit(db, admin.org_id, admin.id, "disabled", user.id)
    db.commit()
    db.refresh(user)
    return user


def set_own_password(db: DbSession, user: User, session_id: int, current_password: str | None, new_password: str) -> None:
    """Change the signed-in user's password and sign out their other sessions."""
    if not user.must_set_password:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise InvalidCredentials()
    check_password_policy(new_password, user.email)

    user.password_hash = hash_password(new_password)
    user.must_set_password = False
    user.password_changed_at = utcnow()
    sessions.revoke_all_for_user(db, user.id, except_session_id=session_id)
    audit(db, user.org_id, user.id, "password_changed", user.id)
    db.commit()
