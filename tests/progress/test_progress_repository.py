from datetime import date

from sqlalchemy.exc import IntegrityError

from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserDB


def test_daily_progress_log_allows_one_row_per_user_date(progress_db_factory):
    db = progress_db_factory()
    user = UserDB(
        username="tester",
        username_normalized="tester",
        email="tester@example.com",
        email_normalized="tester@example.com",
        hashed_password="x",
        role="user",
    )
    db.add(user)
    db.flush()
    db.add(DailyProgressLogDB(user_id=user.id, tanggal=date(2026, 7, 23)))
    db.commit()

    db.add(DailyProgressLogDB(user_id=user.id, tanggal=date(2026, 7, 23)))
    try:
        db.commit()
        raised = False
    except IntegrityError:
        db.rollback()
        raised = True

    assert raised is True
    db.close()
