from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import UserProfile
from app.db.session import SessionLocal
from app.schemas.profile import UserProfileResponse, UserProfileUpdateRequest


DEFAULT_USER_ID = "default_user"


@dataclass(frozen=True)
class ProfileMemory:
    user_id: str
    default_location: str | None = None
    default_task_type: str | None = None
    default_start_time: str | None = None
    default_end_time: str | None = None
    output_style: str | None = None
    common_locations: list[str] | None = None
    common_task_types: list[str] | None = None

    def to_context(self) -> dict[str, object]:
        context = {
            "location": self.default_location,
            "task_type": self.default_task_type,
            "start_time": self.default_start_time,
            "end_time": self.default_end_time,
        }
        return {key: value for key, value in context.items() if value not in (None, [], "")}


def normalize_user_id(user_id: str | None) -> str:
    value = (user_id or "").strip()
    return value or DEFAULT_USER_ID


def get_or_create_user_profile(user_id: str | None = None) -> ProfileMemory:
    normalized_user_id = normalize_user_id(user_id)
    with SessionLocal() as session:
        profile = _get_or_create_profile_row(session=session, user_id=normalized_user_id)
        session.commit()
        return _to_profile_memory(profile)


def update_profile_from_parsed(*, user_id: str | None, parsed: dict[str, object]) -> None:
    normalized_user_id = normalize_user_id(user_id)
    with SessionLocal() as session:
        profile = _get_or_create_profile_row(session=session, user_id=normalized_user_id)
        _apply_parsed_preferences(profile=profile, parsed=parsed)
        session.commit()


def get_user_profile_response(*, session: Session, user_id: str) -> UserProfileResponse:
    profile = _get_or_create_profile_row(session=session, user_id=normalize_user_id(user_id))
    session.flush()
    return _to_profile_response(profile)


def update_user_profile(
    *,
    session: Session,
    user_id: str,
    payload: UserProfileUpdateRequest,
) -> UserProfileResponse:
    profile = _get_or_create_profile_row(session=session, user_id=normalize_user_id(user_id))
    update_data = payload.model_dump(exclude_unset=True)

    for field in [
        "default_location",
        "default_task_type",
        "default_start_time",
        "default_end_time",
        "output_style",
    ]:
        if field in update_data:
            value = update_data[field]
            setattr(profile, field, _clean_optional_string(value))

    if "common_locations" in update_data:
        profile.common_locations_json = _clean_string_list(update_data["common_locations"], limit=10)
    if "common_task_types" in update_data:
        profile.common_task_types_json = _clean_string_list(update_data["common_task_types"], limit=6)

    session.commit()
    session.refresh(profile)
    return _to_profile_response(profile)


def merge_profile_context(
    *,
    session_context: dict[str, object] | None,
    profile: ProfileMemory,
) -> dict[str, object] | None:
    profile_context = profile.to_context()
    if not session_context and not profile_context:
        return None
    merged = dict(profile_context)
    if session_context:
        merged.update(session_context)
    return merged


def _get_or_create_profile_row(*, session: Session, user_id: str) -> UserProfile:
    profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).one_or_none()
    if profile:
        return profile

    profile = UserProfile(
        user_id=user_id,
        default_task_type="cruise",
        output_style="concise",
        common_locations_json=[],
        common_task_types_json=["cruise"],
    )
    session.add(profile)
    session.flush()
    return profile


def _apply_parsed_preferences(*, profile: UserProfile, parsed: dict[str, object]) -> None:
    location = parsed.get("location")
    locations = parsed.get("locations")
    task_type = parsed.get("task_type")

    if isinstance(location, str) and location.strip():
        profile.default_location = profile.default_location or location.strip()
        profile.common_locations_json = _append_unique(profile.common_locations_json, location.strip(), limit=10)

    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, str) and item.strip():
                profile.default_location = profile.default_location or item.strip()
                profile.common_locations_json = _append_unique(profile.common_locations_json, item.strip(), limit=10)

    if isinstance(task_type, str) and task_type.strip():
        profile.default_task_type = profile.default_task_type or task_type.strip()
        profile.common_task_types_json = _append_unique(profile.common_task_types_json, task_type.strip(), limit=6)


def _append_unique(values: object, item: str, *, limit: int) -> list[str]:
    existing = [str(value) for value in values] if isinstance(values, list) else []
    result = [item]
    result.extend(value for value in existing if value != item)
    return result[:limit]


def _to_profile_memory(profile: UserProfile) -> ProfileMemory:
    return ProfileMemory(
        user_id=profile.user_id,
        default_location=profile.default_location,
        default_task_type=profile.default_task_type,
        default_start_time=profile.default_start_time,
        default_end_time=profile.default_end_time,
        output_style=profile.output_style,
        common_locations=[str(item) for item in profile.common_locations_json or []],
        common_task_types=[str(item) for item in profile.common_task_types_json or []],
    )


def _to_profile_response(profile: UserProfile) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=profile.user_id,
        default_location=profile.default_location,
        default_task_type=profile.default_task_type,
        default_start_time=profile.default_start_time,
        default_end_time=profile.default_end_time,
        output_style=profile.output_style,
        common_locations=[str(item) for item in profile.common_locations_json or []],
        common_task_types=[str(item) for item in profile.common_task_types_json or []],
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


def _clean_optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_string_list(values: object, *, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= limit:
            break
    return result
