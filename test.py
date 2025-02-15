import pyaudio
import websockets
import asyncio
import logging
from collections import deque

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Audio configuration
FORMAT = pyaudio.paInt16  # 16-bit audio
CHANNELS = 1  # Mono audio
RATE = 48000  # Sample rate (48 kHz)
CHUNK = 4800  # Chunk size (100ms of audio at 48 kHz)
BUFFER_SECONDS = 3  # Send audio every 3 seconds

# WebSocket server URL
WEBSOCKET_URL = "ws://127.0.0.1:8000/ws/detect-quotes"
API_KEY = "e8ce358cf4d831935f6138e4b777c8c73c5b6f6051ab2aa5ced6b8d66a564f1e"

async def send_audio(websocket):
    """
    Captures audio from the microphone and sends it to the WebSocket server every 3 seconds.

    This function continuously records audio from the default microphone using PyAudio, 
    buffers it for a specified duration (`BUFFER_SECONDS`), and then sends the accumulated 
    audio data to the WebSocket server.

    Args:
        websocket (WebSocketClientProtocol): An active WebSocket connection.

    Raises:
        Exception: Logs any errors that occur during audio capture or WebSocket communication.

    Notes:
        - Uses a `deque` to store audio chunks and sends them as a single payload every `BUFFER_SECONDS`.
        - The WebSocket connection is expected to handle raw audio data.
        - Handles exceptions gracefully and ensures proper resource cleanup.
    """
    audio = pyaudio.PyAudio()

    # Open the microphone stream
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    logging.info("Starting audio capture...")

    try:
        buffer = deque()  # Buffer to store audio chunks
        chunks_per_buffer = int(RATE / CHUNK * BUFFER_SECONDS)  # Number of chunks for 3 seconds

        while True:
            # Read audio data from the microphone
            audio_data = stream.read(CHUNK, exception_on_overflow=False)
            buffer.append(audio_data)

            # If the buffer has enough chunks for 3 seconds, send it
            if len(buffer) >= chunks_per_buffer:
                # Combine chunks into a single byte array
                combined_data = b"".join(buffer)
                logging.info(f"Sending {BUFFER_SECONDS} seconds of audio (size: {len(combined_data)} bytes)")

                # Send the combined audio data to the WebSocket server
                await websocket.send(combined_data)
                logging.info(f"Sent {BUFFER_SECONDS} seconds of audio to WebSocket server")

                # Clear the buffer
                buffer.clear()

    except Exception as e:
        logging.error(f"Error in audio capture or WebSocket communication: {e}")
    finally:
        # Clean up
        stream.stop_stream()
        stream.close()
        audio.terminate()
        logging.info("Audio capture stopped")


async def connect_to_websocket():
    """
    Establishes a WebSocket connection to the server and starts sending audio.

    This function connects to the WebSocket server using the provided `WEBSOCKET_URL`
    and `API_KEY`. Once connected, it calls `send_audio()` to continuously stream 
    audio data.

    Raises:
        Exception: If the WebSocket connection fails.

    Notes:
        - The WebSocket URL must include a valid API key for authentication.
        - The connection is maintained until the program is stopped.
        - Uses `websockets.connect` to establish an asynchronous WebSocket connection.
    """
    async with websockets.connect(f"{WEBSOCKET_URL}?api_key={API_KEY}") as websocket:
        logging.info("Connected to WebSocket server")
        await send_audio(websocket)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(connect_to_websocket())
