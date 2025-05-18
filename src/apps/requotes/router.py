import asyncio
from sqlalchemy import select, update, text
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from sqlalchemy.sql import func
from apps.requotes.models import User,UserActivity,Achievement
from core.database import aget_db
from core.security import verify_api_key
from apps.requotes.services import QuoteDetectionService
from apps.requotes.models import Verse, Version
import logging
from uuid import uuid4, UUID as PyUUID
from typing import Optional




router = APIRouter()


async def award_achievement(session, user, name, tag, requirement):
    """Check if a user qualifies for an achievement and award it if not already given."""
    existing_achievement = await session.execute(
        select(Achievement).where(Achievement.user_id == user.id, Achievement.tag == tag)
    )
    if not existing_achievement.scalar_one_or_none():
        new_achievement = Achievement(user_id=user.id, name=name, tag=tag, requirement=requirement)
        session.add(new_achievement)
        await session.commit()


async def track_verse_catch(session, user, book_name):
    """Track caught verses and handle rewards."""
    try:
        print(f"Tracking verse catch for user {user.email}, book: {book_name}")

        # Create a new UserActivity record for the verse catch
        new_activity = UserActivity(
            user_id=user.id,
            activity_type="verse_caught",
            activity_data=book_name,  # Store the book name or verse details
            activity_date=datetime.utcnow(),
        )
        session.add(new_activity)
        print("Created new UserActivity record for verse_caught")

        

        # Count total verses caught
        total_verses = await session.scalar(
            select(func.count()).where(
                UserActivity.user_id == user.id, 
                UserActivity.activity_type == "verse_caught"
            )
        )
        print(f"Total verses caught: {total_verses}")
        
        # Increase faith_coins by 2
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(faith_coins=User.faith_coins + 2)
        )
        await session.refresh(user)
        print(f"Updated faith_coins to {user.faith_coins}")

        # Award "Verse Catcher" after 100 verses
        if total_verses >= 100:  # Change this to 100 for the actual requirement
            print("Awarding Verse Catcher achievement")
            await award_achievement(session, user, "Verse Catcher", "Verse Catcher", "Catch 100 verses")

        # Track unique books caught
        unique_books = await session.scalars(
            select(UserActivity.activity_data).where(
                UserActivity.user_id == user.id, 
                UserActivity.activity_type == "verse_caught"
            ).distinct()
        )
        unique_books = set(unique_books) | {book_name}
        print(f"Unique books caught: {unique_books}")

        # Award "Bible Explorer" after catching verses from 5 unique books
        if len(unique_books) >= 60:
            print("Awarding Bible Explorer achievement")
            await award_achievement(session, user, "Bible Explorer", "Bible Explorer", "Catch from 60 Unique books")

        # Commit changes to the database
        await session.commit()
        print("done committing updates")

    except Exception as e:
        print(f"Error in track_verse_catch: {e}")
        await session.rollback()
        raise



async def track_sharing(session, user):
    """Track shared verses and award 'Sharing Saint' tag."""
    total_shared = await session.scalar(
        select(func.count()).where(UserActivity.user_id == user.id, UserActivity.activity_type == "verse_shared")
    )

    if total_shared >= 50:
        await award_achievement(session, user, "Sharing Saint", "Sharing Saint", "Share 50 caught Verses")

    await session.commit()


@router.post("/api/track-verse-catch/")
async def executeTrackVerseCatch(data: dict, session: AsyncSession = Depends(aget_db)):
    try:
        print(f"Received data: {data}")
        user = await session.scalar(select(User).where(User.email == data["email"]))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        await track_verse_catch(session, user, data["book_name"])
    except HTTPException as he:
        print(f"HTTPException in track_verse_catch: {he.detail}")
        raise he
    except Exception as e:
        print(f"Error in track_verse_catch: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

async def increment_capture_count(
    session: AsyncSession,
    user_id: Optional[PyUUID] = None,
    anonymous_id: Optional[str] = None
) -> int:
    """
    Atomically increments the capture count for a user (logged-in or anonymous).
    Returns the new total count.
    """
    if not user_id and not anonymous_id:
        raise ValueError("Either user_id or anonymous_id must be provided")

    # Upsert logic (PostgreSQL syntax)
    result = await session.execute(text("""
        INSERT INTO verse_captures (user_id, anonymous_id, count)
        VALUES (:user_id, :anonymous_id, 1)
        ON CONFLICT (COALESCE(user_id, anonymous_id))  -- Ensures uniqueness
        DO UPDATE SET 
            count = verse_captures.count + 1,
            last_captured_at = NOW()
        RETURNING count
    """), {"user_id": user_id, "anonymous_id": anonymous_id})

    await session.commit()
    return result.scalar()


async def process_audio_queue(
    websocket: WebSocket,
    session: AsyncSession,
    queue: asyncio.Queue,
    version: str
):
    while True:
        audio_chunk = await queue.get()
        if audio_chunk is None:
            break

        try:
            # Initialize detector (don't share session)
            detector = QuoteDetectionService(session, audio_chunk, version=version)
            await detector.scan_for_quotes()
            
            if detector.quote_detected:
                print("QUOTE DETECTED")
                user_id = None
                anonymous_id = None

                if websocket.user_email:
                    print("User Is Logged In")
                    result = await session.execute(
                        select(User.id).where(User.email == websocket.user_email)
                    )
                    user_id = result.scalar()
                    
                    if user_id is None:
                        print("User not found, falling back to anonymous")
                        anonymous_id = str(uuid4())
                else:
                    anonymous_id = str(uuid4())
                    print("USER IS Anonymous")

                # Unified tracking
                tracking_id = user_id if user_id is not None else anonymous_id
                id_type = "user_id" if user_id is not None else "anonymous_id"
                
                if tracking_id:
                    print(f"Attempting DB update as {id_type}...")
                    try:
                        # Use execute + commit instead of transaction block
                        await session.execute(
                            text(f"""
                            INSERT INTO verse_captures ({id_type}, count)
                            VALUES (:tracking_id, 1)
                            ON CONFLICT ({id_type})
                            DO UPDATE SET 
                                count = verse_captures.count + 1,
                                last_captured_at = NOW()
                            """),
                            {"tracking_id": tracking_id}
                        )
                        await session.commit()
                        print("DONE UPDATING VERSECAPTURES")
                    except Exception as e:
                        print(f"DB update failed: {str(e)}")
                        await session.rollback()
                        raise
                
                await websocket.send_json([q.model_dump() for q in detector.quotes])
                
        except Exception as e:
            print(f"Error processing audio chunk: {e}")
            await websocket.send_json({"error": str(e)})
        finally:
            queue.task_done()

@router.websocket("/ws/detect-quotes")
async def websocket_endpoint(
    websocket: WebSocket,
    session: AsyncSession = Depends(aget_db),
):
    """
    WebSocket endpoint for detecting quotes in real-time audio streams.

    This WebSocket endpoint allows clients to send audio chunks for real-time 
    quote detection. The received audio data is processed asynchronously using 
    `process_audio_queue`, which scans for quotes and sends detected quotes 
    back to the client.

    Args:
        websocket (WebSocket): The WebSocket connection used for receiving audio data 
                               and sending detected quotes.
        session (AsyncSession): A database session dependency for interacting with the database.

    Behavior:
        - The client must provide a valid `api_key` as a query parameter for authentication.
        - If authentication fails, the WebSocket is closed with status code `WS_1008_POLICY_VIOLATION`.
        - If authentication succeeds, the WebSocket connection is accepted.
        - Audio chunks sent by the client are placed into an `asyncio.Queue` for processing.
        - A background task (`process_audio_queue`) processes the audio data.
        - The connection remains open until the client disconnects or an error occurs.
        - When the connection is closed, the processing task is safely shut down.

    Exceptions:
        - `WebSocketDisconnect`: Raised when the client disconnects.
        - Other exceptions are logged, but the WebSocket is closed safely.

    Notes:
        - The `process_audio_queue` function runs as a separate task and will process 
          incoming audio chunks asynchronously.
        - Upon disconnection, a `None` value is added to the queue to signal termination 
          of the processing task before closing the WebSocket connection.

    """
    api_key = websocket.query_params.get("api_key")
    version = websocket.query_params.get("version")
    user_email = websocket.query_params.get("user_email")
    
    print(user_email)

    if not verify_api_key(api_key):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Store user_email in the WebSocket object for later use
    websocket.user_email = user_email

    audio_queue = asyncio.Queue()
    processing_task = asyncio.create_task(process_audio_queue(websocket, session, audio_queue, version))

    try:
        while True:
            audio_chunk = await websocket.receive_bytes()
            await audio_queue.put(audio_chunk)

    except WebSocketDisconnect:
        print("WebSocket disconnected by client")
    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")
    finally:
        await audio_queue.put(None)
        await processing_task

        await websocket.close()
        print("WebSocket connection closed")


# Set up logging
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

@router.get("/api/get-book/{book_name}")
async def get_book(book_name: str, version_name: str, session: AsyncSession = Depends(aget_db)):
    try:
        # logger.debug(f"Fetching book: {book_name}, version: {version_name}")

        # Join Verse and Version tables and filter by Version.name and Verse.book
        query = (
            select(Verse)
            .join(Version, Verse.version_id == Version.id)
            .where(
                Version.name == version_name,
                Verse.book == book_name
            )
            .order_by(Verse.chapter, Verse.verse_number)
        )

        result = await session.execute(query)
        verses = result.scalars().all()

        # logger.debug(f"Found {len(verses)} verses for book: {book_name}, version: {version_name}")

        if not verses:
            # logger.warning(f"No verses found for book: {book_name}, version: {version_name}")
            raise HTTPException(status_code=404, detail="Book or version not found")

        # Group verses by chapter
        chapters = {}
        for verse in verses:
            if verse.chapter not in chapters:
                chapters[verse.chapter] = []
            chapters[verse.chapter].append({
                "verse_number": verse.verse_number,
                "text": verse.text
            })

        # Convert to list of chapters
        book_data = [{"chapter": chapter, "verses": verses} for chapter, verses in chapters.items()]

        # logger.debug(f"Returning book data for {book_name}: {len(book_data)} chapters")
        return book_data

    except HTTPException as he:
        # logger.error(f"HTTPException in get_book: {he.detail}")
        raise he
    except Exception as e:
        # logger.error(f"Unexpected error in get_book: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")