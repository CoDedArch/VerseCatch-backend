import io
from typing import List, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel
import wave

from core.config import settings

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def create_wav_buffer(raw_data, sample_rate=48000, channels=1, sample_width=2):
    """
    Creates an in-memory WAV file buffer from raw PCM audio data.

    This function takes raw PCM audio data and encodes it into a WAV file format 
    using the specified audio parameters. The generated WAV file is stored in an 
    in-memory `BytesIO` buffer, making it easy to use without writing to disk.

    Args:
        raw_data (bytes): The raw PCM audio data to be written to the WAV file.
        sample_rate (int, optional): The sample rate of the audio in Hz. Defaults to 48000 Hz.
        channels (int, optional): The number of audio channels (1 for mono, 2 for stereo). Defaults to 1 (mono).
        sample_width (int, optional): The sample width in bytes (e.g., 2 for 16-bit audio). Defaults to 2.

    Returns:
        io.BytesIO: A `BytesIO` buffer containing the generated WAV file.
                    The buffer's `.name` attribute is set to "file.wav" for convenience.

    Notes:
        - The function uses the `wave` module to format the audio data into a WAV file.
        - The buffer is rewound to the beginning (`seek(0)`) before returning.
        - The resulting buffer can be used for streaming, HTTP responses, or further processing.
    """
    wav_buffer = io.BytesIO()

    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width) 
        wav_file.setframerate(sample_rate)  
        wav_file.writeframes(raw_data)

    wav_buffer.seek(0)
    wav_buffer.name = "file.wav"
    return wav_buffer



async def transcript_to_text(audio_chunk: bytes) -> str:
    """
    Transcribes an audio chunk into text using OpenAI's Whisper model.

    This function takes raw audio data, converts it into a WAV file buffer, 
    and sends it to OpenAI's Whisper transcription service asynchronously. 
    The transcribed text is then returned.

    Args:
        audio_chunk (bytes): The raw PCM audio data to be transcribed.

    Returns:
        str: The transcribed text from the audio.

    Raises:
        Exception: If the transcription process fails, an error message is printed.

    Notes:
        - The function uses `create_wav_buffer` to convert raw audio data into 
          a WAV format before sending it for transcription.
        - The Whisper model (`whisper-1`) is used for processing.
        - If an exception occurs, it is caught and logged, but no specific 
          error handling is implemented beyond printing the error.
    """
    try:
        buffer = create_wav_buffer(audio_chunk)
        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=buffer,
        )
        return transcription.text

    except Exception as e:
        print("Could not transcribe", e)


class QuoteId(BaseModel):
    book: str
    chapter: int
    verse_number: int


class QuoteIds(BaseModel):
    ids: List[QuoteId]


prompt = """\
You are a precise Bible quote identification system. Given any input text, identify and extract only definitive Bible quotes (not paraphrases or similar-sounding passages).

## Output Format
For each quote found, provide:
- Book: The Bible book name in lowercase (e.g., genesis, psalms, matthew)
- Chapter: The chapter number as an integer
- Verse: The verse number as an integer

## Rules
1. Only extract quotes that are explicitly referenced or clearly identifiable as Bible verses
2. Ignore paraphrases or similar-sounding religious text
3. If a quote is ambiguous or uncertain, exclude it
4. Book names must be in lowercase
5. Chapter and verse numbers must be integers
6. Include partial verses only if they are clearly identified as such

#! IMPORTANT: Do not assume quotes. If not's not mentioned well, don't output it.

## Output Structure
[
    {
        "book": str,
        "chapter": int,
        "verse_number": int,
    },
    ...
]
"""

async def detect_quotes(text: str) -> Optional[List[QuoteId]]:
    """
    Detects quotes in a given text using OpenAI's GPT-4o-mini model.

    This function sends the input text to OpenAI's chat completion API with a predefined 
    system prompt to identify and extract quote IDs. The response is parsed into a list 
    of `QuoteId` objects.

    Args:
        text (str): The input text to analyze for quotes.

    Returns:
        Optional[List[QuoteId]]: A list of detected `QuoteId` objects if quotes are found, 
        or `None` if the input text is empty.

    Raises:
        Exception: If the API request fails, an error may occur (not explicitly handled here).

    Notes:
        - If `text` is empty, the function returns `None` immediately.
        - Uses OpenAI's `gpt-4o-mini` model with a structured system prompt (`prompt`).
        - The response is expected in a structured format defined by `QuoteIds`.
        - Ensure `client.beta.chat.completions.parse` is properly configured for structured outputs.
    """
    if not text:
        return

    completion = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        response_format=QuoteIds,
    )

    return completion.choices[0].message.parsed.ids
