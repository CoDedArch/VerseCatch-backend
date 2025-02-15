from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import joinedload

from .openai import transcript_to_text, detect_quotes, QuoteId
from ..schemas import Quote
from ..models import Verse, Version


class QuoteDetectionService:
    def __init__(self, session: AsyncSession, audio_chunk: bytes, version: str):
        self.audio_chunk = audio_chunk
        self.session = session
        self.quote_detected = False
        self.quotes: List[Quote] = []
        self.version_name = version
    

    async def set_version(self):
        version_stm = select(Version).where(Version.name == self.version_name)
        self.version = (await self.session.execute(version_stm)).scalars().one()

    async def _retrieve_quotes(self, quote_ids: List[QuoteId]):
        """
        Retrieve quotes from the database using the provided quote IDs.
        """
        if not quote_ids:
            return
        
        if not hasattr(self, "version"):
            await self.set_version()

        # Create a list of conditions to filter the verses based on the quote_ids
        conditions = []
        for quote_id in quote_ids:
            conditions.append(
                (Verse.book == quote_id.book.title()) &
                (Verse.chapter == quote_id.chapter) &
                (Verse.verse_number == quote_id.verse_number)
            )

        # Combine the conditions using the OR operator
        combined_condition = or_(*conditions)

        # Build the query with the combined condition and filter by version
        stmt = select(Verse).where(
            Verse.version_id == self.version.id
        ).where(
            combined_condition
        )

        result = await self.session.execute(stmt)
        verses = result.scalars().all()

        self.quotes = [
            Quote(
                version=self.version_name,
                book=verse.book,
                chapter=verse.chapter,
                verse_number=verse.verse_number,
                text=verse.text
            )
            for verse in verses
        ]

        if self.quotes:
            self.quote_detected = True

    async def scan_for_quotes(self):
        text = await transcript_to_text(audio_chunk=self.audio_chunk)
        print("Transcribed text:", text)
        quotes_ids = await detect_quotes(text=text)
        await self._retrieve_quotes(quote_ids=quotes_ids)

    def get_quotes(self) -> List[Verse]:
        return self.quotes
