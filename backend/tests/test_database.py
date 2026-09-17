from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import CandidateProfile


def test_candidate_profile_persists_and_updates(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with session_factory() as session:
        profile = CandidateProfile(
            full_name="Ada Lovelace",
            email="ada@example.com",
            education="BSc Mathematics",
            degree="BSc Mathematics",
            specialization="Computing",
            experience_level="early-career",
            career_interests=["backend engineering", "data engineering"],
            target_roles=["Backend Engineer"],
            skills=["Python", "SQL"],
            career_goals="Build reliable services.",
        )
        session.add(profile)
        session.commit()
        profile_id = profile.id
        original_updated_at = profile.updated_at

    with session_factory() as session:
        persisted = session.scalar(select(CandidateProfile).where(CandidateProfile.id == profile_id))
        assert persisted is not None
        assert persisted.career_interests == ["backend engineering", "data engineering"]
        assert persisted.target_roles == ["Backend Engineer"]
        assert persisted.skills == ["Python", "SQL"]
        assert isinstance(persisted.created_at, datetime)

        persisted.experience_level = "mid-career"
        session.commit()

    with session_factory() as session:
        updated = session.get(CandidateProfile, profile_id)
        assert updated is not None
        assert updated.experience_level == "mid-career"
        assert updated.updated_at >= original_updated_at

    engine.dispose()


def test_test_database_isolated_from_application_database(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'isolated.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)

    with sessionmaker(bind=engine)() as session:
        session.add(CandidateProfile(full_name="Test User", email="test@example.com"))
        session.commit()
        assert session.scalar(select(CandidateProfile).where(CandidateProfile.email == "test@example.com"))

    assert not (tmp_path / "ai_career_companion.db").exists()
    engine.dispose()