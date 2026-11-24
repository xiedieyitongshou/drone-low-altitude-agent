"""One conflict contract for task writes, including ORM flushes of history."""

from contextlib import contextmanager

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError


class MissionTaskVersionConflictError(Exception):
    error_code = "TASK_VERSION_CONFLICT"
    status_code = 409

    def __init__(self, message: str = "任务已发生变化，本次结果未应用，请刷新后重新操作。") -> None:
        super().__init__(message)


class MissionTaskVersionRequiredError(MissionTaskVersionConflictError):
    error_code = "TASK_VERSION_REQUIRED"
    status_code = 428


def require_task_version(version: int | None) -> int:
    if version is None:
        raise MissionTaskVersionRequiredError("请先读取任务，再携带 expected_version 提交操作。")
    return version


def check_task_version(task, expected_version: int | None) -> None:
    if expected_version is not None and task.version != expected_version:
        raise MissionTaskVersionConflictError()


@contextmanager
def task_write_transaction(db: Session):
    try:
        yield
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise MissionTaskVersionConflictError() from exc
    except Exception:
        db.rollback()
        raise
