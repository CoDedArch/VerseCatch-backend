import os
import sys

# Add the project root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import json
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.requotes.models import Verse, Version
from _db import session_manager


DATA_DIR = "../../data"

async def load_json_files():
    """Load all JSON files from the data directory."""
    json_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    all_data = []

    for json_file in json_files:
        version_name = os.path.splitext(json_file)[0]  

        with open(os.path.join(DATA_DIR, json_file), "r", encoding="utf-8") as f:
            data = json.load(f)
            all_data.append({"version": version_name, "books": data}) 

    return all_data


async def populate_database():
    """Populate the database with Bible versions, books, chapters, and verses."""
    async with session_manager.get_session() as session:
        bible_data = await load_json_files()

        for version_data in bible_data:
            version_name = version_data["version"]

            result = await session.execute(select(Version).where(Version.name == version_name))
            existing_version = result.scalars().first()

            if existing_version:
                print(f"Version '{version_name}' already exists. Skipping...")
                version = existing_version
            else:
                version = Version(id=uuid4(), name=version_name)
                session.add(version)
                await session.commit()
                print(f"Inserted Bible version: {version_name}")

            for book_name, chapters in version_data["books"].items():
                for chapter_num, verses in chapters.items():
                    for verse_num, verse_text in verses.items():
                        verse = Verse(
                            id=uuid4(),
                            version_id=version.id,
                            book=book_name,
                            chapter=int(chapter_num),
                            verse_number=int(verse_num),
                            text=verse_text,
                        )
                        session.add(verse)

            await session.commit()
            print(f"Inserted verses for version: {version_name}")

        print("Database seeding complete!")


if __name__ == "__main__":
    asyncio.run(populate_database())
