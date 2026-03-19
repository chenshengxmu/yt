import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'yt_data.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id         TEXT PRIMARY KEY,
            title      TEXT NOT NULL,
            channel    TEXT,
            duration   INTEGER,
            thumbnail  TEXT,
            filename   TEXT,
            filesize   INTEGER,
            width      INTEGER,
            height     INTEGER,
            url        TEXT NOT NULL,
            status     TEXT DEFAULT 'pending',
            progress   REAL DEFAULT 0.0,
            error_msg  TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts
        USING fts5(id UNINDEXED, title, channel, content='videos', content_rowid='rowid');

        CREATE TRIGGER IF NOT EXISTS videos_ai AFTER INSERT ON videos BEGIN
            INSERT INTO videos_fts(rowid, id, title, channel)
            VALUES (new.rowid, new.id, new.title, new.channel);
        END;

        CREATE TRIGGER IF NOT EXISTS videos_ad AFTER DELETE ON videos BEGIN
            INSERT INTO videos_fts(videos_fts, rowid, id, title, channel)
            VALUES ('delete', old.rowid, old.id, old.title, old.channel);
        END;

        CREATE TRIGGER IF NOT EXISTS videos_au AFTER UPDATE ON videos BEGIN
            INSERT INTO videos_fts(videos_fts, rowid, id, title, channel)
            VALUES ('delete', old.rowid, old.id, old.title, old.channel);
            INSERT INTO videos_fts(rowid, id, title, channel)
            VALUES (new.rowid, new.id, new.title, new.channel);
        END;
    """)
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_video(video_id: str, url: str, title: str = "Fetching..."):
    conn = get_conn()
    ts = now_iso()
    conn.execute(
        """INSERT OR IGNORE INTO videos (id, title, url, status, progress, created_at, updated_at)
           VALUES (?, ?, ?, 'pending', 0.0, ?, ?)""",
        (video_id, title, url, ts, ts)
    )
    conn.commit()
    conn.close()


def update_video(video_id: str, **kwargs):
    if not kwargs:
        return
    kwargs['updated_at'] = now_iso()
    fields = ', '.join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [video_id]
    conn = get_conn()
    conn.execute(f"UPDATE videos SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_video(video_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_videos(page: int = 1, per_page: int = 50):
    offset = (page - 1) * per_page
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM videos WHERE status = 'done' ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM videos WHERE status = 'done'").fetchone()[0]
    conn.close()
    return [dict(r) for r in rows], total


def delete_video(video_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()


def search_videos(query: str, limit: int = 50):
    # Escape special FTS5 characters and add prefix wildcard
    escaped = query.replace('"', '""')
    fts_query = f'"{escaped}"*'
    conn = get_conn()
    rows = conn.execute(
        """SELECT v.* FROM videos v
           JOIN videos_fts f ON v.rowid = f.rowid
           WHERE videos_fts MATCH ? AND v.status = 'done'
           ORDER BY rank
           LIMIT ?""",
        (fts_query, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
