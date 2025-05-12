import os
import sys
import asyncio
import json
from uuid import uuid4
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from apps.requotes.models import Verse, Version, Theme
from core.database._db import session_manager
from core.config import settings

DATA_DIR = os.path.join(os.path.dirname(__file__), settings.DATA_DIR)

async def load_bible_data():
    """Load Bible JSON files from data directory."""
    json_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    if not json_files:
        print("⚠️ No Bible JSON files found in data directory")
        return []

    all_data = []
    for json_file in json_files:
        version_name = os.path.splitext(json_file)[0]
        try:
            with open(os.path.join(DATA_DIR, json_file), "r", encoding="utf-8") as f:
                data = json.load(f)
                all_data.append({
                    "version": version_name,
                    "books": data
                })
        except Exception as e:
            print(f"❌ Failed to load {json_file}: {str(e)}")
    return all_data

async def seed_versions_and_verses(session: AsyncSession):
    """Seed Bible versions and verses."""
    bible_data = await load_bible_data()
    if not bible_data:
        return False

    for version_data in bible_data:
        version_name = version_data["version"]

        # Check if version exists
        version = await session.execute(
            select(Version).where(Version.name == version_name))
        version = version.scalars().first()

        if not version:
            version = Version(id=uuid4(), name=version_name)
            session.add(version)
            await session.commit()
            print(f"✅ Inserted version: {version_name}")

        # Insert verses
        verse_count = 0
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
                    verse_count += 1

        await session.commit()
        print(f"📖 Inserted {verse_count} verses for {version_name}")

    return True

async def seed_themes(session: AsyncSession):
    """Seed theme data from settings."""
    if not hasattr(settings, "THEMES") or not settings.THEMES:
        print("⚠️ No themes found in settings")
        return False

    seeded_count = 0
    for theme_data in settings.THEMES:
        # Check if theme exists
        existing_theme = await session.execute(
            select(Theme).where(Theme.name == theme_data["name"]))
        if existing_theme.scalars().first():
            continue

        theme = Theme(
            id=uuid4(),
            name=theme_data["name"],
            display_name=theme_data["display_name"],
            price=theme_data.get("price", 0),
            preview_image_url=theme_data.get("preview_image_url", ""),
            is_default=theme_data.get("is_default", False),
            styles=json.dumps(theme_data.get("styles", {}))
        )
        session.add(theme)
        seeded_count += 1
        print(f"🎨 Added theme: {theme.display_name}")

    if seeded_count > 0:
        await session.commit()
        print(f"🌈 Seeded {seeded_count} themes")
    else:
        print("🎨 All themes already exist")

    return True

async def main():
    """Main seeding function with error handling."""
    try:
        print("🛠️ Initializing session manager...")
        await session_manager.init()
        print("✅ Session manager initialized")
        async with session_manager.get_session() as session:
            print("\n🚀 Starting database seeding...")

            # Run seeds with success tracking
            results = await asyncio.gather(
                seed_versions_and_verses(session),
                seed_themes(session),
                return_exceptions=True
            )

            # Check results
            if any(isinstance(r, Exception) for r in results):
                for r in results:
                    if isinstance(r, Exception):
                        print(f"🔥 Error: {str(r)}")
                raise Exception("Seeding failed")

            print("\n🎉 All seeding completed successfully!")

    except Exception as e:
        print(f"\n❌ Critical seeding error: {str(e)}")
        raise

    finally:
        await session_manager.close()
        print("🛑 Database session closed")

if __name__ == "__main__":
    asyncio.run(main())