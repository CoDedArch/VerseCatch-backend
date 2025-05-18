from datetime import datetime
from typing import List
from uuid import uuid4, UUID as PyUUID
from sqlalchemy import ForeignKey, String, Integer, text, Column, Boolean, DateTime, CheckConstraint, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from sqlalchemy.sql import func
from core.database import Base
from sqlalchemy import JSON, Index
from sqlalchemy.types import TypeDecorator, VARCHAR
from sqlalchemy.ext.hybrid import hybrid_property
import json
from sqlalchemy.sql import expression

class JSONEncodedDict(TypeDecorator):
    """Represents a JSON-encoded dictionary."""
    
    impl = VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value

class VerseCapture(Base):
    __tablename__ = "verse_captures"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4()
    )
    user_id: Mapped[Optional[PyUUID]] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True
    )
    anonymous_id: Mapped[Optional[str]] = mapped_column(
        String(36), unique=True, nullable=True
    )
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_captured_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL) OR (anonymous_id IS NOT NULL)",
            name="ck_verse_captures_has_id"
        ),
    )

    
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
    requirement: Mapped[str] = mapped_column(String, nullable=False)
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
    last_inspirational_verse: Mapped[str] = mapped_column(JSONEncodedDict, nullable=True)
    next_inspirational_verse_time: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    needs_next_verse: Mapped[bool] = mapped_column(Boolean, default=False)
    is_supporter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_rated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    achievements: Mapped[List["Achievement"]] = relationship(
        "Achievement", back_populates="user", cascade="all, delete-orphan"
    )

    activities: Mapped[List["UserActivity"]] = relationship(
        "UserActivity", back_populates="user", cascade="all, delete-orphan"
    )

    themes: Mapped[List["UserTheme"]] = relationship(
        "UserTheme", back_populates="user", cascade="all, delete-orphan"
    )

    payments: Mapped[List["Payment"]] = relationship(
    "Payment", back_populates="user", cascade="all, delete-orphan"
    )

    ratings: Mapped[List["Rating"]] = relationship(
    "Rating", back_populates="user", cascade="all, delete-orphan"
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

    def check_next_verse_status(self):
        """Check if the user needs the next verse based on the countdown."""
        current_status = self.needs_next_verse
        new_status = bool(self.next_inspirational_verse_time and datetime.utcnow() >= self.next_inspirational_verse_time)
        
        if current_status != new_status:
            self.needs_next_verse = new_status
            return True  
        return False
    
    @hybrid_property
    def rating_description(self) -> Optional[str]:
        if not self.rating:
            return None
        rating_descriptions = {
            1: "Worse - Needs work",
            2: "Good - Has potential",
            3: "Better - Good but could improve",
            4: "Best - Really enjoying it",
            5: "Excellent - Perfect experience!"
        }
        return rating_descriptions.get(self.rating)

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


# Add to your models.py
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[PyUUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="GHS")
    paystack_reference: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, success, failed
    payment_method: Mapped[str] = mapped_column(String, nullable=True)
    payment_metadata: Mapped[dict] = mapped_column(  # Changed from 'metadata' to 'payment_metadata'
        JSONEncodedDict, 
        name="metadata",
        comment="Stores payment metadata like donation type and original USD amount"
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount > 0", name="check_amount_positive"),
    )

    @property
    def is_successful(self) -> bool:
        return self.status == "success"
    

class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[PyUUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="ratings")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
    )