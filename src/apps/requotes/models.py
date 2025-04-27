from datetime import datetime
from typing import List
from uuid import uuid4, UUID as PyUUID
from sqlalchemy import ForeignKey, String, Integer, text, Column, Boolean, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from core.database import Base
from sqlalchemy import JSON



class Version(Base):
    __tablename__ = "bible_versions"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    name: Mapped[str] = mapped_column(String, unique=True)

    verses: Mapped[List["Verse"]] = relationship(
        "Verse", back_populates="version", cascade="all, delete-orphan"
    )


class Verse(Base):
    __tablename__ = "bible_verses"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    version_id: Mapped[PyUUID] = mapped_column(ForeignKey("bible_versions.id"))
    book: Mapped[str] = mapped_column(String, index=True)
    chapter: Mapped[int] = mapped_column(Integer, index=True)
    verse_number: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(String)

    version: Mapped["Version"] = relationship("Version", back_populates="verses")


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[PyUUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    requirement: Mapped[int] = mapped_column(Integer, nullable=False)
    achieved_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="achievements")


class UserActivity(Base):
    __tablename__ = "user_activities"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[PyUUID] = mapped_column(ForeignKey("users.id"))
    activity_type: Mapped[str] = mapped_column(String, nullable=False)
    activity_data: Mapped[str] = mapped_column(String, nullable=True)
    activity_date: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="activities")


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preview_image_url: Mapped[str] = mapped_column(String, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    styles: Mapped[dict] = mapped_column(JSON, nullable=True)


class UserTheme(Base):
    __tablename__ = "user_themes"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[PyUUID] = mapped_column(ForeignKey("users.id"))
    theme_id: Mapped[PyUUID] = mapped_column(ForeignKey("themes.id"))
    unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unlocked_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    unlocked_via_ad: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="themes")
    theme: Mapped["Theme"] = relationship("Theme")


class User(Base):
    __tablename__ = "users"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    streak: Mapped[int] = mapped_column(Integer, default=0, index=True)
    faith_coins: Mapped[int] = mapped_column(Integer, default=0, index=True)
    current_tag: Mapped[str] = mapped_column(String, default="Newbie", nullable=False)
    last_login = Column(DateTime, nullable=True)
    bible_version = Column(String, nullable=True)
    has_taken_tour: Mapped[bool] = mapped_column(Boolean, default=False)
    current_theme_id: Mapped[PyUUID] = mapped_column(ForeignKey("themes.id"), nullable=True)
    achievements: Mapped[List["Achievement"]] = relationship(
        "Achievement", back_populates="user", cascade="all, delete-orphan"
    )
    activities: Mapped[List["UserActivity"]] = relationship(
        "UserActivity", back_populates="user", cascade="all, delete-orphan"
    )
    themes: Mapped[List["UserTheme"]] = relationship(
        "UserTheme", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("streak >= 0", name="check_streak_non_negative"),
        CheckConstraint("faith_coins >= 0", name="check_faith_coins_non_negative"),
    )

    @property
    def logged_in_today(self) -> bool:
        if not self.last_login:
            return False
        return self.last_login.date() == datetime.utcnow().date()

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, streak={self.streak})>"
    
class UnverifiedUser(Base):
    __tablename__ = "unverified_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    bible_version = Column(String)
    verification_token = Column(String)