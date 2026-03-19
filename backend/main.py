import os
import sys

# Ensure project root is on path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.database import init_db, get_video, list_videos, delete_video, search_videos, update_video
from backend.downloader import start_download, extract_video_id
from backend.streamer import stream_video

BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
VIDEOS_DIR = os.path.join(BASE_DIR, 'videos')
THUMBNAILS_DIR = os.path.join(BASE_DIR, 'thumbnails')

app = FastAPI(title="YT Downloader")

# Initialize DB on startup
init_db()

# Static files
app.mount("/thumbnails", StaticFiles(directory=THUMBNAILS_DIR), name="thumbnails")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


class DownloadRequest(BaseModel):
    url: str


@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.post("/api/download")
async def download(req: DownloadRequest, background_tasks: BackgroundTasks):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    video_id = extract_video_id(url)
    if not video_id:
        # Try to get ID via yt-dlp for non-standard URLs
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'nocheckcertificate': True, 'cookiesfrombrowser': ('chrome', '/Users/chensheng/Library/Application Support/Google/Chrome/Profile 1')}) as ydl:
                info = ydl.extract_info(url, download=False)
                video_id = info.get('id')
        except Exception:
            raise HTTPException(status_code=400, detail="Could not parse YouTube video ID from URL")

    if not video_id:
        raise HTTPException(status_code=400, detail="Could not parse YouTube video ID from URL")

    existing = get_video(video_id)
    if existing and existing['status'] == 'done':
        return {"id": video_id, "status": "done", "message": "Already downloaded"}

    background_tasks.add_task(start_download, video_id, url)
    return {"id": video_id, "status": "pending"}


@app.get("/api/videos")
async def videos(page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200)):
    items, total = list_videos(page=page, per_page=per_page)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


@app.get("/api/status/{video_id}")
async def status(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {
        "id": video["id"],
        "status": video["status"],
        "progress": video["progress"],
        "title": video["title"],
        "error_msg": video.get("error_msg"),
    }


@app.get("/api/search")
async def search(q: str = Query(..., min_length=1)):
    results = search_videos(q)
    return {"items": results, "total": len(results)}


@app.get("/api/stream/{video_id}")
async def stream(video_id: str, request: Request):
    video = get_video(video_id)
    if not video or video["status"] != "done":
        raise HTTPException(status_code=404, detail="Video not found or not ready")

    filename = video.get("filename")
    if not filename:
        raise HTTPException(status_code=404, detail="Video file not found")

    filepath = os.path.join(BASE_DIR, filename)

    ext = os.path.splitext(filename)[1].lower()
    content_type_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
    }
    content_type = content_type_map.get(ext, "video/mp4")

    return await stream_video(request, filepath, content_type)


@app.delete("/api/videos/{video_id}")
async def delete(video_id: str):
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Delete files
    for field in ("filename", "thumbnail"):
        path = video.get(field)
        if path:
            full_path = os.path.join(BASE_DIR, path)
            if os.path.exists(full_path):
                os.remove(full_path)

    delete_video(video_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
