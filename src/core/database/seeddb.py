import os
import sys
from pathlib import Path

# Add the project root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import json
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.requotes.models import Verse, Version, Theme
from _db import session_manager

THEMES = [
    {
        "name": "default",
        "display_name": "Default",
        "price": 0,
        "preview_image_url": "/assets/themes/default.jpg",
        "is_default": True,
        "styles": {
            "mainBackground": {
                "background": "animated-gradient",
            },
            "taskBackground": {
                "background": "linear-gradient(135deg, rgba(20, 30, 48, 1), rgba(36, 59, 85, 0.2))",
                "color": "#ffffff",
                "contentBackground": "rgba(255, 255, 255, 0.1)"
            },
            "verseBackground": {
                "background": "linear-gradient(135deg, rgba(20, 30, 48, 1), rgba(36, 59, 85, 0.2))",
                "color": "#ffffff",
                "verseHighlight": "#fef08a"  # text-yellow-300 equivalent
            },
            "interactionBackground": {
                "background": "#ffffff",  # bg-white equivalent
                "color": "#1f2937",  # text-gray-800 equivalent
                "buttonColor": "#000000"  # bg-black equivalent
            }
        }
    },
    {
        "name": "dark-night",
        "display_name": "Dark Night",
        "price": 20,
        "preview_image_url": "/assets/themes/dark-night.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "#111827"  # bg-gray-900 equivalent
            },
            "taskBackground": {
                "background": "linear-gradient(135deg, #1a1a2e, #16213e)",
                "color": "#e5e7eb",  # text-gray-200 equivalent
                "contentBackground": "rgba(255, 255, 255, 0.05)"
            },
            "verseBackground": {
                "background": "linear-gradient(135deg, #1a1a2e, #16213e)",
                "color": "#f3f4f6",  # text-gray-100 equivalent
                "verseHighlight": "#93c5fd"  # text-blue-300 equivalent
            },
            "interactionBackground": {
                "background": "#1f2937",  # bg-gray-800 equivalent
                "color": "#ffffff",
                "buttonColor": "#4f46e5"  # bg-indigo-600 equivalent
            }
        }
    },
    {
        "name": "sunrise",
        "display_name": "Sunrise",
        "price": 75,
        "preview_image_url": "/assets/themes/sunrise.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom, #ffedd5, #fef3c7)"  # from-orange-100 to-yellow-50
            },
            "taskBackground": {
                "background": "linear-gradient(135deg, #ff9a9e, #fad0c4)",
                "color": "#1f2937",  # text-gray-800 equivalent
                "contentBackground": "rgba(255, 255, 255, 0.3)"
            },
            "verseBackground": {
                "background": "linear-gradient(135deg, #ff9a9e, #fad0c4)",
                "color": "#111827",  # text-gray-900 equivalent
                "verseHighlight": "#dc2626"  # text-red-600 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #fef9c3, #fed7aa)",  # from-yellow-100 to-orange-100
                "color": "#1f2937",  # text-gray-800 equivalent
                "buttonColor": "#f97316"  # bg-orange-500 equivalent
            }
        }
    },
    {
        "name": "ocean-breeze",
        "display_name": "Ocean Breeze",
        "price": 6,
        "preview_image_url": "/assets/themes/ocean-breeze.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #eff6ff, #cffafe)"  # from-blue-50 to-cyan-100
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #a8edea, #fed6e3)",
                "color": "#1f2937",  # text-gray-800 equivalent
                "contentBackground": "rgba(255,255,255,0.5)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #c2e9fb, #a1c4fd)",
                "color": "#111827",  # text-gray-900 equivalent
                "verseHighlight": "#1d4ed8"  # text-blue-700 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #dbeafe, #a5f3fc)",  # from-blue-100 to-cyan-100
                "color": "#1f2937",  # text-gray-800 equivalent
                "buttonColor": "#0891b2"  # bg-cyan-600 equivalent
            }
        }
    },
    {
        "name": "forest-green",
        "display_name": "Forest Green",
        "price": 65,
        "preview_image_url": "/assets/themes/forest-green.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #f0fdf4, #d1fae5)"  # from-green-50 to-emerald-100
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #d4fc79, #96e6a1)",
                "color": "#1f2937",  # text-gray-800 equivalent
                "contentBackground": "rgba(255,255,255,0.4)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #96e6a1, #84fab0)",
                "color": "#111827",  # text-gray-900 equivalent
                "verseHighlight": "#15803d"  # text-green-700 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #dcfce7, #a7f3d0)",  # from-green-100 to-emerald-100
                "color": "#1f2937",  # text-gray-800 equivalent
                "buttonColor": "#059669"  # bg-emerald-600 equivalent
            }
        }
    },
    {
        "name": "royal-purple",
        "display_name": "Royal Purple",
        "price": 80,
        "preview_image_url": "/assets/themes/royal-purple.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #f5f3ff, #ede9fe)"  # from-purple-50 to-violet-100
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #c4b5fd, #a78bfa)",
                "color": "#111827",  # text-gray-900 equivalent
                "contentBackground": "rgba(255,255,255,0.3)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #a78bfa, #8b5cf6)",
                "color": "#ffffff",
                "verseHighlight": "#fef08a"  # text-yellow-300 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #ede9fe, #ddd6fe)",  # from-purple-100 to-violet-100
                "color": "#111827",  # text-gray-900 equivalent
                "buttonColor": "#7c3aed"  # bg-violet-600 equivalent
            }
        }
    },
    {
        "name": "fiery-red",
        "display_name": "Fiery Red",
        "price": 70,
        "preview_image_url": "/assets/themes/fiery-red.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #fef2f2, #ffe4e6)"  # from-red-50 to-rose-100
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #ff758c, #ff7eb3)",
                "color": "#111827",  # text-gray-900 equivalent
                "contentBackground": "rgba(255,255,255,0.3)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #ff7eb3, #ff758c)",
                "color": "#111827",  # text-gray-900 equivalent
                "verseHighlight": "#b91c1c"  # text-red-700 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #fee2e2, #fecdd3)",  # from-red-100 to-rose-100
                "color": "#111827",  # text-gray-900 equivalent
                "buttonColor": "#e11d48"  # bg-rose-600 equivalent
            }
        }
    },
    {
        "name": "golden-hour",
        "display_name": "Golden Hour",
        "price": 85,
        "preview_image_url": "/assets/themes/folden-hour.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #fffbeb, #fef3c7)"  # from-amber-50 to-yellow-100
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #f6d365, #fda085)",
                "color": "#111827",  # text-gray-900 equivalent
                "contentBackground": "rgba(255,255,255,0.3)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #fda085, #f6d365)",
                "color": "#111827",  # text-gray-900 equivalent
                "verseHighlight": "#b45309"  # text-amber-700 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #fef3c7, #fde68a)",  # from-amber-100 to-yellow-100
                "color": "#111827",  # text-gray-900 equivalent
                "buttonColor": "#f59e0b"  # bg-amber-500 equivalent
            }
        }
    },
    {
        "name": "twilight",
        "display_name": "Twilight",
        "price": 90,
        "preview_image_url": "/assets/themes/twilight.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #312e81, #581c87)"  # from-indigo-900 to-purple-900
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #4f46e5, #7c3aed)",
                "color": "#e5e7eb",  # text-gray-200 equivalent
                "contentBackground": "rgba(79, 70, 229, 0.7)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #7c3aed, #9333ea)",
                "color": "#ffffff",
                "verseHighlight": "#fcd34d"  # text-amber-300 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #3730a3, #6b21a8)",  # from-indigo-800 to-purple-800
                "color": "#ffffff",
                "buttonColor": "#9333ea"  # bg-purple-600 equivalent
            }
        }
    },
    {
        "name": "mint-fresh",
        "display_name": "Mint Fresh",
        "price": 4,
        "preview_image_url": "/assets/themes/mint-fresh.jpg",
        "is_default": False,
        "styles": {
            "mainBackground": {
                "background": "linear-gradient(to bottom right, #f0fdf9, #ccfbf1)"  # from-teal-50 to-emerald-100
            },
            "taskBackground": {
                "background": "linear-gradient(145deg, #a1ffce, #faffd1)",
                "color": "#1f2937",  # text-gray-800 equivalent
                "contentBackground": "rgba(255,255,255,0.4)"
            },
            "verseBackground": {
                "background": "linear-gradient(145deg, #faffd1, #a1ffce)",
                "color": "#111827",  # text-gray-900 equivalent
                "verseHighlight": "#0d9488"  # text-teal-600 equivalent
            },
            "interactionBackground": {
                "background": "linear-gradient(to right, #ccfbf1, #a7f3d0)",  # from-teal-100 to-emerald-100
                "color": "#1f2937",  # text-gray-800 equivalent
                "buttonColor": "#10b981"  # bg-emerald-500 equivalent
            }
        }
    }
]




async def seed_themes(session: AsyncSession):
    """Seed the database with theme data."""
    for theme_data in THEMES:
        result = await session.execute(select(Theme).where(Theme.name == theme_data["name"]))
        existing_theme = result.scalars().first()

        if existing_theme:
            print(f"Theme '{theme_data['name']}' already exists. Skipping...")
            continue
        
        # Convert styles dict to JSON string for storage
        styles_json = json.dumps(theme_data["styles"])
        
        theme = Theme(
            id=uuid4(),
            name=theme_data["name"],
            display_name=theme_data["display_name"],
            price=theme_data["price"],
            preview_image_url=theme_data["preview_image_url"],
            is_default=theme_data["is_default"],
            styles=styles_json  # Store styles as JSON string
        )
        session.add(theme)
        print(f"Inserted theme: {theme_data['display_name']}")

    await session.commit()
    print("Theme seeding complete!")


async def main():
    """Main function to run all seeding operations."""
    async with session_manager.get_session() as session:
        print("Starting database seeding...")
        
        # Then seed themes
        await seed_themes(session)
        
        print("All seeding operations completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())