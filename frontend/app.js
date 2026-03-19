'use strict';

// ── State ──────────────────────────────────────────────────────────────────
const activeDownloads = new Map(); // video_id -> { title, progress, status }
let pollTimer = null;
let searchDebounce = null;
let isSearching = false;

// ── DOM refs ───────────────────────────────────────────────────────────────
const urlInput       = document.getElementById('url-input');
const downloadBtn    = document.getElementById('download-btn');
const activeSection  = document.getElementById('active-section');
const activeList     = document.getElementById('active-list');
const videoGrid      = document.getElementById('video-grid');
const searchInput    = document.getElementById('search-input');
const modalOverlay   = document.getElementById('modal-overlay');
const modalTitle     = document.getElementById('modal-title');
const modalFooter    = document.getElementById('modal-footer');
const modalClose     = document.getElementById('modal-close');
const player         = document.getElementById('player');

// ── Utilities ──────────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function fmtDuration(secs) {
  if (!secs) return '';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes > 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
  if (bytes > 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
  return (bytes / 1e3).toFixed(0) + ' KB';
}

// ── Download ───────────────────────────────────────────────────────────────
downloadBtn.addEventListener('click', submitDownload);
urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitDownload(); });

async function submitDownload() {
  const url = urlInput.value.trim();
  if (!url) return;

  downloadBtn.disabled = true;
  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast(data.detail || 'Download failed', 'error');
      return;
    }
    if (data.status === 'done') {
      toast('Already in library!', 'success');
      loadLibrary();
      return;
    }
    activeDownloads.set(data.id, { title: 'Loading...', progress: 0, status: 'pending' });
    urlInput.value = '';
    renderActiveDownloads();
    startPolling();
    toast('Download started', 'success');
  } catch (e) {
    toast('Network error', 'error');
  } finally {
    downloadBtn.disabled = false;
  }
}

// ── Polling ────────────────────────────────────────────────────────────────
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollAll, 1000);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function pollAll() {
  if (activeDownloads.size === 0) { stopPolling(); return; }

  const ids = [...activeDownloads.keys()];
  const results = await Promise.allSettled(ids.map(id =>
    fetch(`/api/status/${id}`).then(r => r.json())
  ));

  let anyCompleted = false;
  results.forEach((result, i) => {
    if (result.status !== 'fulfilled') return;
    const data = result.value;
    const id = ids[i];
    activeDownloads.set(id, {
      title: data.title || id,
      progress: data.progress || 0,
      status: data.status,
      error_msg: data.error_msg,
    });
    if (data.status === 'done') {
      anyCompleted = true;
      setTimeout(() => {
        activeDownloads.delete(id);
        renderActiveDownloads();
      }, 2000);
    }
    if (data.status === 'error') {
      toast(`Error: ${data.error_msg || 'Download failed'}`, 'error');
      setTimeout(() => {
        activeDownloads.delete(id);
        renderActiveDownloads();
      }, 5000);
    }
  });

  renderActiveDownloads();
  if (anyCompleted) loadLibrary();
  if (activeDownloads.size === 0) stopPolling();
}

function renderActiveDownloads() {
  if (activeDownloads.size === 0) {
    activeSection.style.display = 'none';
    activeList.innerHTML = '';
    return;
  }
  activeSection.style.display = '';
  activeList.innerHTML = '';
  for (const [id, info] of activeDownloads) {
    const pct = Math.min(100, Math.round(info.progress || 0));
    const isError = info.status === 'error';
    const isDone  = info.status === 'done';
    const div = document.createElement('div');
    div.className = 'download-item';
    div.innerHTML = `
      <div class="download-item-header">
        <span class="download-title">${escHtml(info.title)}</span>
        <span class="${isError ? 'status-badge status-error' : isDone ? 'status-badge status-done' : 'download-pct'}">
          ${isError ? 'Error' : isDone ? 'Done' : pct + '%'}
        </span>
      </div>
      ${!isError ? `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>` : ''}
      ${isError && info.error_msg ? `<div style="font-size:12px;color:var(--error);margin-top:6px">${escHtml(info.error_msg)}</div>` : ''}
    `;
    activeList.appendChild(div);
  }
}

// ── Library ────────────────────────────────────────────────────────────────
async function loadLibrary(searchQuery = '') {
  try {
    let url = '/api/videos';
    if (searchQuery && searchQuery.length >= 2) {
      url = `/api/search?q=${encodeURIComponent(searchQuery)}`;
    }
    const res = await fetch(url);
    const data = await res.json();
    renderLibrary(data.items || []);
  } catch (e) {
    console.error('Failed to load library', e);
  }
}

function renderLibrary(videos) {
  if (videos.length === 0) {
    videoGrid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-state-icon">📭</div>
        <div>No videos yet. Paste a YouTube URL above to get started.</div>
      </div>`;
    return;
  }
  videoGrid.innerHTML = '';
  for (const v of videos) {
    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.id = v.id;

    const thumb = v.thumbnail
      ? `<img class="card-thumb" src="/${v.thumbnail}" loading="lazy" alt="" />`
      : `<div class="card-thumb-placeholder">▶</div>`;

    card.innerHTML = `
      ${thumb}
      <div class="card-body">
        <div class="card-title">${escHtml(v.title)}</div>
        <div class="card-meta">
          <span>${escHtml(v.channel || '')}</span>
          <span>${fmtDuration(v.duration)}</span>
        </div>
        <div class="card-actions">
          <button class="btn-sm btn-play" data-id="${v.id}" data-title="${escAttr(v.title)}"
            data-channel="${escAttr(v.channel || '')}" data-duration="${v.duration || ''}"
            data-filesize="${v.filesize || ''}">
            ▶ Play
          </button>
          <button class="btn-sm btn-delete" data-id="${v.id}">Delete</button>
        </div>
      </div>`;
    videoGrid.appendChild(card);
  }

  videoGrid.querySelectorAll('.btn-play').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      openPlayer(btn.dataset.id, btn.dataset.title, btn.dataset.channel, btn.dataset.duration, btn.dataset.filesize);
    });
  });

  videoGrid.querySelectorAll('.btn-delete').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      deleteVideo(btn.dataset.id);
    });
  });

  videoGrid.querySelectorAll('.card').forEach(card => {
    card.addEventListener('click', () => {
      const btn = card.querySelector('.btn-play');
      if (btn) btn.click();
    });
  });
}

// ── Player ─────────────────────────────────────────────────────────────────
function openPlayer(id, title, channel, duration, filesize) {
  modalTitle.textContent = title;
  player.src = `/api/stream/${id}`;
  player.load();
  player.play().catch(() => {});

  const parts = [];
  if (channel) parts.push(channel);
  if (duration) parts.push(fmtDuration(parseInt(duration)));
  if (filesize) parts.push(fmtSize(parseInt(filesize)));
  modalFooter.textContent = parts.join(' · ');

  modalOverlay.classList.add('open');
}

function closePlayer() {
  player.pause();
  player.src = '';
  modalOverlay.classList.remove('open');
}

modalClose.addEventListener('click', closePlayer);
modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) closePlayer(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePlayer(); });

// ── Delete ─────────────────────────────────────────────────────────────────
async function deleteVideo(id) {
  if (!confirm('Delete this video?')) return;
  try {
    const res = await fetch(`/api/videos/${id}`, { method: 'DELETE' });
    if (res.ok) {
      toast('Deleted', 'success');
      loadLibrary(searchInput.value.trim());
    } else {
      toast('Delete failed', 'error');
    }
  } catch {
    toast('Network error', 'error');
  }
}

// ── Search ─────────────────────────────────────────────────────────────────
searchInput.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    const q = searchInput.value.trim();
    loadLibrary(q);
  }, 300);
});

// ── Escape helpers ─────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escAttr(str) {
  if (!str) return '';
  return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Init ───────────────────────────────────────────────────────────────────
loadLibrary();
