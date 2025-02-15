from pydantic import BaseModel, Field


class Quote(BaseModel):
    """
    Pydantic model for a Bible quote.
    """

    version: str = Field(..., title="Bible version")
    book: str = Field(..., title="Book of the Bible")
    chapter: int = Field(..., title="Chapter number")
    verse_number: int = Field(..., title="Verse number")
    text: str = Field(..., title="Verse text")

    class Config:
        from_attributes = True
