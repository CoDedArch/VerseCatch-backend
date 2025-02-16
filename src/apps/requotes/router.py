import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import aget_db
from core.security import verify_api_key
from apps.requotes.services import QuoteDetectionService


router = APIRouter()

async def process_audio_queue(websocket: WebSocket, session: AsyncSession, queue: asyncio.Queue):
    """
    Background task to process audio chunks from a queue, detect quotes in the audio,
    and send the detected quotes via a WebSocket.

    This function is an asynchronous task that continuously retrieves audio chunks 
    from the provided queue. For each chunk, it uses the QuoteDetectionService to 
    scan for quotes. If any quotes are detected, they are serialized and sent 
    through the provided WebSocket connection.

    Args:
        websocket (WebSocket): The WebSocket connection used to send detected quotes.
        session (AsyncSession): The database session used for querying or interacting 
                                with the database during quote detection.
        queue (asyncio.Queue): An asyncio queue that holds audio chunks to be processed. 
                               The queue should contain audio chunks that are asynchronously 
                               processed one at a time.

    Returns:
        None

    Raises:
        Any exceptions raised by QuoteDetectionService or WebSocket send operation
        are propagated, and the task will stop processing further chunks if an error occurs.

    Notes:
        - The function runs indefinitely until a `None` value is retrieved from the queue, 
          which signals the task to stop processing.
        - The `quote_detected` attribute of the detector indicates if any quotes were found 
          in the audio chunk.
        - The `model_dump()` method serializes the detected quotes for sending via WebSocket.
    """
    while True:
        audio_chunk = await queue.get()
        if audio_chunk is None:
            break

        detector = QuoteDetectionService(session, audio_chunk, version="ASV_bible")
        await detector.scan_for_quotes()
        if detector.quote_detected:
            await websocket.send_json([q.model_dump() for q in detector.quotes])

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
    if not verify_api_key(api_key):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    audio_queue = asyncio.Queue()
    processing_task = asyncio.create_task(process_audio_queue(websocket, session, audio_queue))

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
