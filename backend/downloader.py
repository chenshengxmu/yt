import os
import threading
from backend.database import create_video, update_video, get_video

BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
VIDEOS_DIR = os.path.join(BASE_DIR, 'videos')
THUMBNAILS_DIR = os.path.join(BASE_DIR, 'thumbnails')


def _run_download(video_id: str, url: str):
    try:
        import yt_dlp

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    pct = downloaded / total * 100
                    update_video(video_id, progress=round(pct, 1), status='downloading')
            elif d['status'] == 'finished':
                update_video(video_id, progress=100.0, status='downloading')

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(VIDEOS_DIR, '%(id)s.%(ext)s'),
            'writethumbnail': True,
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'cookiesfrombrowser': ('chrome', '/Users/chensheng/Library/Application Support/Google/Chrome/Profile 1'),
            'js_runtimes': {'node': {'path': '/usr/local/bin/node'}},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_id_actual = info.get('id', video_id)
        ext = info.get('ext', 'mp4')
        filename = f"videos/{video_id_actual}.{ext}"
        filepath = os.path.join(BASE_DIR, filename)
        filesize = os.path.getsize(filepath) if os.path.exists(filepath) else None

        # Find thumbnail (yt-dlp may write various extensions)
        thumbnail_path = None
        for thumb_ext in ('jpg', 'jpeg', 'webp', 'png'):
            candidate = os.path.join(THUMBNAILS_DIR, f"{video_id_actual}.{thumb_ext}")
            # yt-dlp writes thumbnail next to video, move it to thumbnails/
            src = os.path.join(VIDEOS_DIR, f"{video_id_actual}.{thumb_ext}")
            if os.path.exists(src):
                os.makedirs(THUMBNAILS_DIR, exist_ok=True)
                dest = os.path.join(THUMBNAILS_DIR, f"{video_id_actual}.jpg")
                os.rename(src, dest)
                thumbnail_path = f"thumbnails/{video_id_actual}.jpg"
                break
            if os.path.exists(candidate):
                thumbnail_path = f"thumbnails/{video_id_actual}.jpg"
                break

        update_video(
            video_id,
            title=info.get('title', 'Unknown'),
            channel=info.get('uploader') or info.get('channel', ''),
            duration=info.get('duration'),
            thumbnail=thumbnail_path,
            filename=filename,
            filesize=filesize,
            width=info.get('width'),
            height=info.get('height'),
            status='done',
            progress=100.0,
            error_msg=None,
        )
    except Exception as e:
        update_video(video_id, status='error', error_msg=str(e))


def start_download(video_id: str, url: str):
    existing = get_video(video_id)
    if existing and existing['status'] == 'done':
        return  # Already downloaded

    create_video(video_id, url)
    update_video(video_id, status='downloading', progress=0.0, error_msg=None)

    t = threading.Thread(target=_run_download, args=(video_id, url), daemon=True)
    t.start()


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    import re
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None
