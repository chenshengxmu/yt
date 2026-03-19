import os
import aiofiles
from fastapi import Request
from fastapi.responses import StreamingResponse, Response

BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
CHUNK_SIZE = 64 * 1024  # 64KB


async def stream_video(request: Request, filepath: str, content_type: str = "video/mp4"):
    if not os.path.exists(filepath):
        return Response(status_code=404, content="Video file not found")

    file_size = os.path.getsize(filepath)
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        range_val = range_header.strip().replace("bytes=", "")
        parts = range_val.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        async def generator():
            async with aiofiles.open(filepath, "rb") as f:
                await f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = await f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
        }
        return StreamingResponse(generator(), status_code=206, headers=headers)
    else:
        # Full file
        async def full_generator():
            async with aiofiles.open(filepath, "rb") as f:
                while True:
                    chunk = await f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
        }
        return StreamingResponse(full_generator(), status_code=200, headers=headers)
