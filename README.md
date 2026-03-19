# YT Downloader

A self-hosted YouTube downloader with a web UI. Paste a URL, download in the background, and stream from your local library.

## Features

- Download YouTube videos via URL
- Background downloads with live progress tracking
- In-browser video player with range-request streaming
- Search your local library
- Delete videos and thumbnails

## Stack

- **Backend**: FastAPI + yt-dlp + SQLite
- **Frontend**: Vanilla HTML/CSS/JS

## Setup

```bash
pip install -r requirements.txt
python -m backend.main
```

Open [http://localhost:8000](http://localhost:8000).
