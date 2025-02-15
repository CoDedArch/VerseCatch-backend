from typing import List
from uuid import UUID as PyUUID

from sqlalchemy import ForeignKey, String, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Version(Base):
    """
    SQLAlchemy model for storing Bible versions.
    """

    __tablename__ = "bible_versions"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    name: Mapped[str] = mapped_column(String, unique=True)

    verses: Mapped[List["Verse"]] = relationship(
        "Verse", back_populates="version", cascade="all, delete-orphan"
    )


class Verse(Base):
    """
    SQLAlchemy model for storing Bible verses, linked to a particular version.
    """

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