from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import RuleItem, RuleSet, User


def build_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return TestingSessionLocal()


def test_rule_set_and_rule_items_persist_with_owner_and_visibility():
    with build_session() as db:
        user = User(
            id="user-a",
            username="rule_owner",
            password_hash="hashed",
            role="user",
            is_active=True,
        )
        rule_set = RuleSet(
            id="rules-user-a",
            name="用户巡航规则",
            task_type="cruise",
            owner_user_id="user-a",
            tenant_id="tenant-a",
            visibility="private",
            status="draft",
            version=1,
            source="user",
            items=[
                RuleItem(
                    id="wind-prohibited",
                    metric="wind_speed",
                    operator=">=",
                    threshold_value=25.0,
                    unit="km/h",
                    decision="禁飞",
                    label="风速禁飞阈值",
                    risk_tag="high_wind",
                    priority=10,
                ),
                RuleItem(
                    id="weather-prohibited",
                    metric="weather_text",
                    operator="in",
                    threshold_values_json=["雷雨", "暴雨"],
                    decision="禁飞",
                    label="高风险天气禁飞",
                    risk_tag="storm",
                    priority=20,
                ),
            ],
        )
        db.add_all([user, rule_set])
        db.commit()

        persisted = db.scalar(select(RuleSet).where(RuleSet.id == "rules-user-a"))

        assert persisted is not None
        assert persisted.owner_user_id == "user-a"
        assert persisted.tenant_id == "tenant-a"
        assert persisted.visibility == "private"
        assert persisted.status == "draft"
        assert [item.id for item in persisted.items] == ["wind-prohibited", "weather-prohibited"]
        assert persisted.items[0].threshold_value == 25.0
        assert persisted.items[1].threshold_values_json == ["雷雨", "暴雨"]
