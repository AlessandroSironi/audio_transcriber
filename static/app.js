/* ==========================================================
   Audio Transcriber — Main SPA
   ========================================================== */

document.body.insertAdjacentHTML('afterbegin', '<div class="bg-orbs" aria-hidden="true"></div>');

'use strict';

// ── Theme ────────────────────────────────────────────────
const html = document.documentElement;
const themeBtn = document.getElementById('theme-toggle');
const iconDark = document.getElementById('theme-icon-dark');
const iconLight = document.getElementById('theme-icon-light');

function applyTheme(theme) {
  html.setAttribute('data-theme', theme);
  iconDark.style.display  = theme === 'dark'  ? '' : 'none';
  iconLight.style.display = theme === 'light' ? '' : 'none';
  localStorage.setItem('theme', theme);
}

applyTheme(localStorage.getItem('theme') || 'dark');
themeBtn.addEventListener('click', () => {
  applyTheme(html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
});

// ── Tab routing ──────────────────────────────────────────
const tabBtns  = document.querySelectorAll('.nav-tab');
const pages    = document.querySelectorAll('.page');

function showTab(tabName) {
  tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
  pages.forEach(p => p.classList.toggle('active', p.id === `page-${tabName}`));
  if (tabName === 'library') loadLibrary();
  if (tabName === 'settings') loadSettings();
}

tabBtns.forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));

// ── Toast ────────────────────────────────────────────────
function toast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ── Upload logic ─────────────────────────────────────────
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const filePreview= document.getElementById('file-preview');
const fileNameLbl= document.getElementById('file-name-label');
const fileSizeLbl= document.getElementById('file-size-label');
const clearBtn   = document.getElementById('clear-file-btn');
const startBtn   = document.getElementById('start-btn');
const stopBtn    = document.getElementById('stop-btn');

let selectedFile = null;
let activeJobId  = null;

dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1024**2).toFixed(1)} MB`;
}

function handleFile(file) {
  if (!file) return;
  selectedFile = file;
  fileNameLbl.textContent = file.name;
  fileSizeLbl.textContent = humanSize(file.size);
  filePreview.classList.add('visible');
  document.getElementById('upload-wave').style.display = 'none';
}

clearBtn.addEventListener('click', () => {
  selectedFile = null;
  fileInput.value = '';
  filePreview.classList.remove('visible');
  document.getElementById('upload-wave').style.display = '';
  document.getElementById('progress-wrap').classList.remove('visible');
  resetProgress();
});

// ── Stage timeline ────────────────────────────────────────
const STAGES = ['convert', 'diarize', 'transcribe', 'merge', 'save'];
const STAGE_LABELS = { convert: 'Convert', diarize: 'Diarize', transcribe: 'Transcribe', merge: 'Merge', save: 'Save' };

function buildTimeline() {
  const tl = document.getElementById('stage-timeline');
  tl.innerHTML = '';
  STAGES.forEach((s, i) => {
    if (i > 0) {
      const conn = document.createElement('div');
      conn.className = 'stage-connector';
      conn.id = `conn-${s}`;
      tl.appendChild(conn);
    }
    const node = document.createElement('div');
    node.className = 'stage-node';
    node.id = `stage-${s}`;
    node.innerHTML = `
      <div class="stage-dot">${i + 1}</div>
      <span class="stage-label">${STAGE_LABELS[s]}</span>
    `;
    tl.appendChild(node);
  });
}

function setStageActive(stageName) {
  let passed = true;
  STAGES.forEach((s, i) => {
    const node = document.getElementById(`stage-${s}`);
    if (!node) return;
    if (s === stageName) {
      node.className = 'stage-node active';
      passed = false;
    } else if (passed) {
      node.className = 'stage-node done';
      if (i > 0) {
        const conn = document.getElementById(`conn-${s}`);
        if (conn) conn.classList.add('done');
      }
    } else {
      node.className = 'stage-node';
    }
  });
}

function resetProgress() {
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-bar').classList.remove('running');
  document.getElementById('progress-bar').style.background = '';
  document.getElementById('progress-log').textContent = '';
  stopBtn.style.display = 'none';
  buildTimeline();
}

buildTimeline();

// ── Stop button ───────────────────────────────────────────
stopBtn.addEventListener('click', () => {
  if (!activeJobId) return;
  stopBtn.disabled = true;
  stopBtn.textContent = 'Stopping …';
  fetch(`/api/jobs/${activeJobId}/cancel`, { method: 'POST' }).catch(() => {});
});

// ── Transcription job ─────────────────────────────────────
startBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  startBtn.disabled = true;
  startBtn.textContent = 'Uploading …';

  const fd = new FormData();
  fd.append('file', selectedFile);

  let jobId;
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    jobId = data.job_id;
    activeJobId = jobId;
  } catch (err) {
    toast(`Upload failed: ${err.message}`, 'error');
    startBtn.disabled = false;
    startBtn.textContent = 'Transcribe';
    return;
  }

  // Show progress section
  document.getElementById('progress-wrap').classList.add('visible');
  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  bar.classList.add('running');
  bar.style.width = '0%';
  bar.style.background = '';
  log.textContent = 'Connecting …';
  stopBtn.style.display = '';
  stopBtn.disabled = false;
  stopBtn.textContent = '⏹ Stop';

  // Open WebSocket
  const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${wsProto}://${location.host}/ws/${jobId}`);

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.stage === 'ping') return;

    const pct = msg.pct ?? 0;
    bar.style.width = `${pct}%`;
    log.textContent = msg.message || msg.stage;

    // Map stage name or pct to timeline
    const stageMap = { convert: 'convert', diarize: 'diarize', transcribe: 'transcribe', merge: 'merge', save: 'save' };
    if (stageMap[msg.stage]) {
      setStageActive(stageMap[msg.stage]);
    } else if (pct <= 10)      setStageActive('convert');
    else if (pct <= 45)  setStageActive('diarize');
    else if (pct <= 85)  setStageActive('transcribe');
    else if (pct <= 99)  setStageActive('merge');

    if (msg.stage === 'done') {
      bar.classList.remove('running');
      bar.style.width = '100%';
      STAGES.forEach(s => {
        document.getElementById(`stage-${s}`).className = 'stage-node done';
        const conn = document.getElementById(`conn-${s}`);
        if (conn) conn.classList.add('done');
      });
      log.textContent = 'Transcription complete!';
      startBtn.disabled = false;
      startBtn.textContent = 'Transcribe';
      stopBtn.style.display = 'none';
      activeJobId = null;
      toast('Transcription complete!', 'success');
      if (msg.result_id) openViewer(msg.result_id);
    }

    if (msg.stage === 'cancelled') {
      bar.classList.remove('running');
      bar.style.background = 'var(--yellow)';
      log.textContent = 'Transcription cancelled.';
      startBtn.disabled = false;
      startBtn.textContent = 'Transcribe';
      stopBtn.style.display = 'none';
      activeJobId = null;
      toast('Transcription cancelled', 'info');
    }

    if (msg.stage === 'error') {
      bar.classList.remove('running');
      bar.style.background = 'var(--red)';
      log.textContent = `Error: ${msg.error}`;
      startBtn.disabled = false;
      startBtn.textContent = 'Transcribe';
      stopBtn.style.display = 'none';
      activeJobId = null;
      toast(`Error: ${msg.error}`, 'error', 6000);
    }
  };

  ws.onerror = () => {
    toast('WebSocket error — check server logs', 'error');
    startBtn.disabled = false;
    startBtn.textContent = 'Transcribe';
    stopBtn.style.display = 'none';
    activeJobId = null;
  };
});

// ── System resource stats ─────────────────────────────────
let _sysStatsTimer = null;

function fmtMb(mb) {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

function startSysStats() {
  const bar = document.getElementById('sys-stats-bar');
  bar.style.display = '';
  if (_sysStatsTimer) return;
  updateSysStats();
  _sysStatsTimer = setInterval(updateSysStats, 3000);
}

async function updateSysStats() {
  try {
    const res = await fetch('/api/system');
    const d = await res.json();
    document.getElementById('stat-cpu').textContent =
      `CPU ${d.cpu_pct.toFixed(0)}%`;
    document.getElementById('stat-ram').textContent =
      `RAM ${fmtMb(d.ram_used_mb)} / ${fmtMb(d.ram_total_mb)} (${d.ram_pct}%)`;
    if (d.gpu_total_mb != null) {
      const label = d.gpu_type === 'mps' ? 'GPU (MPS)' : 'GPU';
      document.getElementById('stat-gpu').textContent =
        `${label} ${fmtMb(d.gpu_used_mb)} / ${fmtMb(d.gpu_total_mb)} (${d.gpu_pct}%)`;
      document.getElementById('stat-gpu').style.display = '';
      document.getElementById('stat-gpu-divider').style.display = '';
    }
  } catch {}
}

// Start stats when upload page is visible
startSysStats();

// ── Library ───────────────────────────────────────────────
const searchInput = document.getElementById('library-search');
let _txList = [];
let _sortKey = 'title';
let _sortDir = 'asc';

async function loadLibrary() {
  const grid = document.getElementById('tx-grid');
  try {
    const res = await fetch('/api/transcriptions');
    _txList = await res.json();
    renderLibrary(applyFilters(_txList));
  } catch {
    grid.innerHTML = '<p style="color:var(--red)">Failed to load transcriptions.</p>';
  }
}

function durationToSecs(dur) {
  if (!dur) return 0;
  const p = dur.split(':').map(Number);
  return p.length === 3 ? p[0]*3600 + p[1]*60 + p[2] : p.length === 2 ? p[0]*60 + p[1] : 0;
}

function sortList(list) {
  return [...list].sort((a, b) => {
    let va, vb;
    switch (_sortKey) {
      case 'date':
        va = new Date(a.date || 0).getTime();
        vb = new Date(b.date || 0).getTime();
        break;
      case 'title':
        va = (a.title || a.result_id || '').toLowerCase();
        vb = (b.title || b.result_id || '').toLowerCase();
        break;
      case 'model':
        va = (a.model || '').toLowerCase();
        vb = (b.model || '').toLowerCase();
        break;
      case 'duration':
        va = durationToSecs(a.duration);
        vb = durationToSecs(b.duration);
        break;
      case 'speakers':
        va = a.speakers || 0;
        vb = b.speakers || 0;
        break;
      default: return 0;
    }
    if (va < vb) return _sortDir === 'asc' ? -1 : 1;
    if (va > vb) return _sortDir === 'asc' ? 1 : -1;
    return 0;
  });
}

function applyFilters(list) {
  const q = searchInput.value.toLowerCase();
  const filtered = q
    ? list.filter(tx => (tx.title || tx.result_id || '').toLowerCase().includes(q))
    : list;
  return sortList(filtered);
}

// Sort bar wiring
document.querySelectorAll('.sort-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    _sortKey = btn.dataset.sort;
    document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderLibrary(applyFilters(_txList));
  });
});

const sortDirBtn = document.getElementById('sort-dir-btn');
sortDirBtn.addEventListener('click', () => {
  _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
  sortDirBtn.textContent = _sortDir === 'desc' ? '↓' : '↑';
  renderLibrary(applyFilters(_txList));
});

function relativeTime(iso) {
  if (!iso) return '';
  const delta = (Date.now() - new Date(iso)) / 1000;
  if (delta < 60)    return 'Just now';
  if (delta < 3600)  return `${Math.floor(delta/60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta/3600)}h ago`;
  return `${Math.floor(delta/86400)}d ago`;
}

function renderLibrary(list) {
  const grid = document.getElementById('tx-grid');
  if (!list.length) {
    grid.innerHTML = `<div class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      <p>No transcriptions yet.</p>
    </div>`;
    return;
  }
  grid.innerHTML = list.map((tx, i) => `
    <div class="tx-card" data-id="${tx.result_id}" style="animation-delay:${i*50}ms">
      <div class="tx-card-header">
        <div class="tx-card-title">${escHtml(tx.title || tx.result_id)}</div>
        <button type="button" class="tx-card-edit-btn" data-id="${tx.result_id}" title="Edit">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
        </button>
      </div>
      <div style="font-size:.78rem;color:var(--text-dim)">${relativeTime(tx.date)}</div>
      <div class="tx-meta">
        ${tx.duration ? `<span class="pill">${tx.duration}</span>` : ''}
        ${tx.speakers ? `<span class="pill green">${tx.speakers} speaker${tx.speakers > 1 ? 's' : ''}</span>` : ''}
        ${tx.model ? `<span class="pill accent">${tx.model}</span>` : ''}
        ${tx.device ? `<span class="pill">${tx.device}</span>` : ''}
      </div>
    </div>
  `).join('');
  grid.querySelectorAll('.tx-card').forEach(card => {
    card.addEventListener('click', e => {
      if (e.target.closest('.tx-card-edit-btn')) return;
      openViewer(card.dataset.id);
    });
  });
  grid.querySelectorAll('.tx-card-edit-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const tx = _txList.find(t => t.result_id === btn.dataset.id);
      if (tx) openEditModal(tx);
    });
  });
}

searchInput.addEventListener('input', () => renderLibrary(applyFilters(_txList)));

document.getElementById('refresh-library-btn').addEventListener('click', loadLibrary);

// ── Edit modal ────────────────────────────────────────────
let _editingResultId = null;

function toDatetimeLocal(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function openEditModal(tx) {
  _editingResultId = tx.result_id;
  document.getElementById('edit-title-input').value = tx.title || '';
  document.getElementById('edit-date-input').value = toDatetimeLocal(tx.date);
  document.getElementById('edit-modal').classList.add('open');
  document.getElementById('edit-title-input').focus();
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.remove('open');
  _editingResultId = null;
}

document.getElementById('edit-modal-close').addEventListener('click', closeEditModal);
document.getElementById('edit-modal-cancel').addEventListener('click', closeEditModal);
document.getElementById('edit-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('edit-modal')) closeEditModal();
});

document.getElementById('edit-modal-save').addEventListener('click', async () => {
  if (!_editingResultId) return;
  const title = document.getElementById('edit-title-input').value.trim();
  const dateVal = document.getElementById('edit-date-input').value;
  if (!title) { toast('Title cannot be empty', 'error'); return; }

  const btn = document.getElementById('edit-modal-save');
  btn.disabled = true;
  btn.textContent = 'Saving …';

  const updates = { title };
  if (dateVal) {
    const d = new Date(dateVal);
    const pad = n => String(n).padStart(2, '0');
    updates.date = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  const savedId = _editingResultId;
  try {
    const res = await fetch(`/api/transcriptions/${savedId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error(await res.text());
    toast('Saved', 'success');
    closeEditModal();
    await loadLibrary();
    if (_currentResultId === savedId) openViewer(savedId);
  } catch (err) {
    toast(`Save failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save';
  }
});

// Keyboard shortcut: Escape closes modal
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && document.getElementById('edit-modal').classList.contains('open')) {
    closeEditModal();
  }
});

// ── Viewer ────────────────────────────────────────────────
let _currentResultId = null;
let _currentMarkdown = '';
let _currentMeta = {};

async function openViewer(resultId) {
  _currentResultId = resultId;
  showTab('viewer');
  document.getElementById('viewer-tab-btn').style.display = '';
  document.getElementById('viewer-body').innerHTML =
    '<div style="color:var(--text-muted);padding:20px">Loading …</div>';

  try {
    const res = await fetch(`/api/transcriptions/${resultId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _currentMarkdown = data.markdown || '';
    _currentMeta = data.metadata || {};
    renderViewer(_currentMeta, _currentMarkdown);
  } catch (err) {
    document.getElementById('viewer-body').innerHTML =
      `<p style="color:var(--red)">Failed to load transcription: ${escHtml(err.message)}</p>`;
  }
}

function stripFrontMatter(text) {
  if (!text.startsWith('---')) return text;
  // Find the closing --- after the first line
  const closeIdx = text.indexOf('\n---', 3);
  if (closeIdx === -1) return text;
  return text.slice(closeIdx + 4); // skip past the closing ---\n
}

function renderViewer(meta, markdown) {
  // Meta strip
  const strip = document.getElementById('viewer-meta-strip');
  const pills = [
    meta.date    ? `<span class="pill">${new Date(meta.date).toLocaleString()}</span>` : '',
    meta.duration? `<span class="pill">${meta.duration}</span>` : '',
    meta.speakers? `<span class="pill green">${meta.speakers} speaker${meta.speakers>1?'s':''}</span>` : '',
    meta.model   ? `<span class="pill accent">${meta.model}</span>` : '',
    meta.device  ? `<span class="pill">${meta.device}</span>` : '',
  ];
  strip.innerHTML = pills.join('');

  const body = stripFrontMatter(markdown);
  const container = document.getElementById('viewer-body');

  try {
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
      container.innerHTML = marked.parse(body);
    } else {
      container.innerHTML = `<pre style="white-space:pre-wrap;font-size:.88rem">${escHtml(body)}</pre>`;
    }
  } catch (e) {
    container.innerHTML = `<pre style="white-space:pre-wrap;font-size:.88rem">${escHtml(body)}</pre>`;
  }

  // Color-code speaker headings
  const SP_HUES = [240, 287, 340, 28, 75, 170, 200, 55];
  container.querySelectorAll('h2').forEach(h2 => {
    const m = h2.textContent.match(/Speaker (\d+)/i);
    if (m) {
      const n = Math.min(parseInt(m[1]), 8);
      const hue = SP_HUES[n - 1];
      h2.style.cssText = `
        border-left: 3px solid var(--sp${n});
        color: var(--sp${n});
        padding: 6px 12px;
        background: hsla(${hue},60%,60%,.08);
        box-shadow: inset 4px 0 14px hsla(${hue},60%,60%,.14);
        border-radius: 4px;
        display: inline-block;
        margin: 20px 0 8px;
      `;
    }
  });
}

document.getElementById('back-to-library-btn').addEventListener('click', () => showTab('library'));

document.getElementById('edit-tx-btn').addEventListener('click', () => {
  if (!_currentResultId) return;
  openEditModal({ result_id: _currentResultId, ..._currentMeta });
});

function _fallbackCopy(text) {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;pointer-events:none';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('Copied to clipboard', 'success');
  } catch { toast('Copy failed', 'error'); }
}

document.getElementById('copy-md-btn').addEventListener('click', () => {
  const text = _currentMarkdown;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text)
      .then(() => toast('Copied to clipboard', 'success'))
      .catch(() => _fallbackCopy(text));
  } else {
    _fallbackCopy(text);
  }
});

document.getElementById('download-md-btn').addEventListener('click', () => {
  const blob = new Blob([_currentMarkdown], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${_currentResultId}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
});

document.getElementById('delete-tx-btn').addEventListener('click', () => {
  if (!_currentResultId) return;
  if (!confirm(`Delete transcription "${_currentResultId}"?`)) return;
  fetch(`/api/transcriptions/${_currentResultId}`, { method: 'DELETE' })
    .then(() => {
      toast('Deleted', 'success');
      document.getElementById('viewer-tab-btn').style.display = 'none';
      showTab('library');
    })
    .catch(() => toast('Delete failed', 'error'));
});

// ── Settings ──────────────────────────────────────────────
let _hwData = null;
let _selectedModel = null;

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const cfg = await res.json();
    document.getElementById('setting-storage-dir').value = cfg.storage_dir || '';
    document.getElementById('setting-device-override').value = cfg.device_override || '';
    _selectedModel = cfg.whisper_model;
  } catch {}

  try {
    const [hwRes, modelsRes] = await Promise.all([
      fetch('/api/hardware'),
      fetch('/api/models'),
    ]);
    _hwData = await hwRes.json();
    const modelStatus = await modelsRes.json();
    renderHwStrip(_hwData);
    renderModelCards(_hwData, _selectedModel, modelStatus);
  } catch {
    document.getElementById('hw-strip').innerHTML =
      '<span style="color:var(--red)">Hardware info unavailable</span>';
  }
}

function renderHwStrip(hw) {
  const strip = document.getElementById('hw-strip');
  strip.innerHTML = `
    <span class="hw-item"><strong>${hw.accelerator_name}</strong></span>
    <span class="hw-item">Accelerator: <strong>${hw.accelerator.toUpperCase()}</strong></span>
    ${hw.vram_total_mb > 0
      ? `<span class="hw-item">VRAM: <strong>${fmtMb(hw.vram_free_mb)} free</strong> / ${fmtMb(hw.vram_total_mb)} total</span>`
      : ''}
    <span class="hw-item">RAM: <strong>${fmtMb(hw.ram_free_mb)} free</strong> / ${fmtMb(hw.ram_total_mb)} total</span>
  `;
}

function renderModelCards(hw, selected, modelStatus = {}) {
  const container = document.getElementById('settings-model-cards');
  const caps = hw.model_capabilities;
  const recommended = hw.recommended_model;

  const order = ['tiny', 'base', 'small', 'medium', 'large-v3-turbo', 'large-v3'];
  container.innerHTML = order.map(name => {
    const cap = caps[name] || {};
    const isSelected = name === (selected || 'large-v3');
    const isRec = name === recommended;
    const ms = modelStatus[name] || {};
    const dlBadge = ms.downloaded
      ? `<span class="model-dl-badge downloaded">✓ Downloaded${ms.size_mb ? ` · ${ms.size_mb} MB` : ''}</span>`
      : `<span class="model-dl-badge">Not downloaded</span>`;
    const delBtn = ms.downloaded
      ? `<button type="button" class="model-del-btn" data-model="${name}" title="Delete model files">Delete</button>`
      : '';
    return `
      <div class="model-card ${isSelected ? 'selected' : ''} ${isRec ? 'recommended' : ''}"
           data-model="${name}" role="button" tabindex="0">
        <div class="model-card-header">
          <div class="model-name">${name}</div>
          ${delBtn}
        </div>
        <div class="model-desc">${cap.accuracy || '—'} · ${cap.speed || '—'}</div>
        ${badgeHtml(cap.status)}
        <div class="model-note">${cap.note || ''}</div>
        <div class="model-dl-row">${dlBadge}</div>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.model-card').forEach(card => {
    card.addEventListener('click', e => {
      if (e.target.classList.contains('model-del-btn')) return;
      container.querySelectorAll('.model-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      _selectedModel = card.dataset.model;
    });
  });

  container.querySelectorAll('.model-del-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const modelName = btn.dataset.model;
      if (!confirm(`Delete downloaded files for "${modelName}"?\nYou will need to re-download before using it.`)) return;
      btn.disabled = true;
      btn.textContent = 'Deleting…';
      fetch(`/api/models/${modelName}`, { method: 'DELETE' })
        .then(res => res.ok ? res : res.text().then(t => { throw new Error(t); }))
        .then(() => {
          toast(`Model "${modelName}" deleted`, 'success');
          return Promise.all([fetch('/api/hardware'), fetch('/api/models')]);
        })
        .then(([, modelsRes]) => modelsRes.json())
        .then(newModels => renderModelCards(_hwData, _selectedModel, newModels))
        .catch(err => {
          toast('Delete failed: ' + err.message, 'error');
          btn.disabled = false;
          btn.textContent = 'Delete';
        });
    });
  });
}

function badgeHtml(status) {
  if (!status) return '';
  const icons  = { accelerated: '⚡', tight: '⚠', cpu_only: '○' };
  const labels = { accelerated: 'Accelerated', tight: 'Tight', cpu_only: 'CPU only' };
  return `<span class="capability-badge ${status}">${icons[status] || ''} ${labels[status] || status}</span>`;
}

document.getElementById('save-settings-btn').addEventListener('click', () => {
  const btn = document.getElementById('save-settings-btn');
  btn.disabled = true;
  btn.textContent = 'Saving …';
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      storage_dir: document.getElementById('setting-storage-dir').value,
      whisper_model: _selectedModel,
      device_override: document.getElementById('setting-device-override').value || null,
    }),
  })
    .then(() => {
      btn.textContent = '✓ Saved';
      btn.classList.add('btn-success');
      setTimeout(() => {
        btn.textContent = 'Save settings';
        btn.classList.remove('btn-success');
        btn.disabled = false;
      }, 2000);
      toast('Settings saved', 'success');
    })
    .catch(() => {
      toast('Failed to save settings', 'error');
      btn.disabled = false;
      btn.textContent = 'Save settings';
    });
});

// ── Helpers ───────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Shutdown ──────────────────────────────────────────────
document.getElementById('shutdown-btn').addEventListener('click', () => {
  if (!confirm('Shut down the server? You will need to restart it from the terminal.')) return;

  const btn = document.getElementById('shutdown-btn');
  btn.disabled = true;
  btn.textContent = 'Shutting down …';

  // Connection reset is expected — show overlay regardless of fetch outcome.
  fetch('/api/shutdown', { method: 'POST' })
    .catch(() => {})
    .finally(() => {
      document.getElementById('shutdown-overlay').style.display = 'flex';
    });
});

// Initial load
loadLibrary();
