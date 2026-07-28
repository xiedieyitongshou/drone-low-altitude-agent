from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import User
from app.schemas.admin import AdminUserListResponse, AdminUserResponse


class AdminUserManagementError(Exception):
    pass


class AdminUserNotFoundError(AdminUserManagementError):
    pass


class LastActiveAdminError(AdminUserManagementError):
    pass


def list_admin_users(
    *,
    db: Session,
    page: int = 1,
    page_size: int = 20,
    username: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)

    filters = []
    if username:
        keyword = f"%{username.strip()}%"
        filters.append(or_(User.username.ilike(keyword), User.display_name.ilike(keyword)))
    if role:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active == is_active)

    total_statement = select(func.count()).select_from(User)
    list_statement = select(User).order_by(User.created_at.desc(), User.id.desc())
    if filters:
        total_statement = total_statement.where(*filters)
        list_statement = list_statement.where(*filters)

    total = db.scalar(total_statement) or 0
    users = db.scalars(
        list_statement.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    ).all()

    return AdminUserListResponse(
        items=[to_admin_user_response(user) for user in users],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
    )


def update_user_status(*, db: Session, user_id: str, is_active: bool) -> AdminUserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise AdminUserNotFoundError("user not found")

    if user.role == "admin" and user.is_active and not is_active and _active_admin_count(db) <= 1:
        raise LastActiveAdminError("cannot disable the last active admin")

    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return to_admin_user_response(user)


def update_user_role(*, db: Session, user_id: str, role: str) -> AdminUserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise AdminUserNotFoundError("user not found")

    if user.role == "admin" and role != "admin" and user.is_active and _active_admin_count(db) <= 1:
        raise LastActiveAdminError("cannot downgrade the last active admin")

    user.role = role
    db.commit()
    db.refresh(user)
    return to_admin_user_response(user)


def to_admin_user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _active_admin_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
        )
        or 0
    )
