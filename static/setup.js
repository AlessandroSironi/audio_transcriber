/* ==========================================================
   Audio Transcriber — Setup Wizard JS
   ========================================================== */

'use strict';

// Restore theme
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

// ── Step state ────────────────────────────────────────────
const TOTAL_STEPS = 5;
let currentStep = 1;
let wizardData = JSON.parse(sessionStorage.getItem('wizard') || '{}');

function saveWizard() { sessionStorage.setItem('wizard', JSON.stringify(wizardData)); }

function goTo(n) {
  if (n < 1 || n > TOTAL_STEPS) return;
  document.querySelectorAll('.setup-step').forEach(el => el.classList.remove('active'));
  document.getElementById(`step-${n}`).classList.add('active');

  document.querySelectorAll('.step-crumb').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.remove('active', 'done');
    if (s === n) el.classList.add('active');
    else if (s < n) el.classList.add('done');
  });

  currentStep = n;
  if (n === 3) runSystemCheck();
  if (n === 4) loadModelCards();
}

// Restore progress if page was refreshed
if (wizardData.step) goTo(wizardData.step);

// ── Step 1: Welcome ───────────────────────────────────────
document.getElementById('step1-next').addEventListener('click', () => {
  wizardData.step = 2;
  saveWizard();
  goTo(2);
});

// Pre-fill storage dir default
document.getElementById('setup-storage-dir').value =
  wizardData.storage_dir || '~/AudioTranscriptions';

// ── Step 2: Storage ───────────────────────────────────────
document.getElementById('step2-back').addEventListener('click', () => goTo(1));
document.getElementById('step2-next').addEventListener('click', () => {
  const dir = document.getElementById('setup-storage-dir').value.trim();
  if (!dir) {
    document.getElementById('storage-hint').textContent = 'Please enter a directory path.';
    document.getElementById('storage-hint').style.color = 'var(--red)';
    return;
  }
  wizardData.storage_dir = dir;
  wizardData.step = 3;
  saveWizard();
  goTo(3);
});

// ── Step 3: System check ──────────────────────────────────
document.getElementById('step3-back').addEventListener('click', () => goTo(2));
document.getElementById('step3-next').addEventListener('click', () => {
  wizardData.step = 4;
  saveWizard();
  goTo(4);
});

async function runSystemCheck() {
  const statusEl = document.getElementById('ffmpeg-status');
  const hintEl   = document.getElementById('ffmpeg-hint');
  const nextBtn  = document.getElementById('step3-next');

  statusEl.innerHTML = `<div class="check-item">
    <span class="spinner" style="width:18px;height:18px"></span>
    <div><div class="check-label">Checking ffmpeg …</div></div>
  </div>`;

  try {
    const res = await fetch('/api/setup/check', { method: 'POST' });
    const data = await res.json();
    if (data.ffmpeg) {
      statusEl.innerHTML = `<div class="check-item">
        <span class="check-icon">✅</span>
        <div><div class="check-label">ffmpeg found</div><div class="check-detail">Audio conversion ready</div></div>
      </div>`;
      hintEl.style.display = 'none';
      nextBtn.disabled = false;
    } else {
      statusEl.innerHTML = `<div class="check-item" style="border-color:var(--red)">
        <span class="check-icon">❌</span>
        <div><div class="check-label" style="color:var(--red)">ffmpeg not found</div>
        <div class="check-detail">Install it then reload this page</div></div>
      </div>`;
      hintEl.style.display = 'block';
      hintEl.innerHTML = `
        <div class="form-label" style="margin-bottom:6px">Install ffmpeg:</div>
        ${data.platform === 'darwin'
          ? `<div class="install-hint">brew install ffmpeg</div>`
          : `<div class="install-hint">sudo apt install ffmpeg</div><div class="install-hint" style="margin-top:6px"># or: sudo dnf install ffmpeg</div>`
        }
      `;
      nextBtn.disabled = true;
    }
  } catch {
    statusEl.innerHTML = `<div class="check-item" style="border-color:var(--red)">
      <span class="check-icon">⚠</span>
      <div><div class="check-label" style="color:var(--yellow)">Check failed</div>
      <div class="check-detail">Server may not be ready yet — try refreshing</div></div>
    </div>`;
  }
}

// ── Step 4: Model size ────────────────────────────────────
document.getElementById('step4-back').addEventListener('click', () => goTo(3));
document.getElementById('step4-next').addEventListener('click', async () => {
  const sel = document.querySelector('#setup-model-cards .model-card.selected');
  if (sel) wizardData.whisper_model = sel.dataset.model;
  wizardData.step = 5;
  saveWizard();

  const btn = document.getElementById('step4-next');
  btn.disabled = true;
  btn.textContent = 'Saving …';
  try {
    await saveConfig();
    goTo(5);
  } catch (e) {
    alert(`Failed to save configuration: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Next →';
  }
});

let _hwData = null;

async function loadModelCards() {
  const container = document.getElementById('setup-model-cards');
  try {
    const res = await fetch('/api/hardware');
    _hwData = await res.json();
    const caps = _hwData.model_capabilities;
    const recommended = _hwData.recommended_model;
    const selected = wizardData.whisper_model || recommended;
    document.getElementById('dl-whisper-label').textContent = `Whisper ${selected || 'model'}`;

    const order = ['tiny', 'base', 'small', 'medium', 'large-v3-turbo', 'large-v3'];
    container.innerHTML = order.map(name => {
      const cap = caps[name] || {};
      const isSelected = name === selected;
      const isRec = name === recommended;
      return `
        <div class="model-card ${isSelected ? 'selected' : ''} ${isRec ? 'recommended' : ''}"
             data-model="${escAttr(name)}" role="button" tabindex="0">
          <div class="model-name">${escHtml(name)}</div>
          <div class="model-desc">${escHtml(cap.accuracy || '—')} · ${escHtml(cap.speed || '—')}</div>
          <span class="capability-badge ${badgeClass(cap.status)}">${badgeIcon(cap.status)} ${badgeLabel(cap.status)}</span>
          <div class="model-note">${escHtml(cap.note || '')}</div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.model-card').forEach(card => {
      card.addEventListener('click', () => {
        container.querySelectorAll('.model-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        wizardData.whisper_model = card.dataset.model;
        document.getElementById('dl-whisper-label').textContent = `Whisper ${card.dataset.model}`;
        saveWizard();
      });
    });
  } catch {
    container.innerHTML = '<p style="color:var(--red)">Could not load hardware info.</p>';
  }
}

function badgeIcon(status) {
  return { accelerated: '⚡', tight: '⚠', cpu_only: '○' }[status] || '';
}
function badgeLabel(status) {
  return escHtml({ accelerated: 'Accelerated', tight: 'Tight', cpu_only: 'CPU only' }[status] || status);
}
function badgeClass(status) {
  return ['accelerated', 'tight', 'cpu_only'].includes(status) ? status : '';
}
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function escAttr(str) {
  return escHtml(str).replace(/'/g, '&#39;');
}

async function saveConfig() {
  const res = await fetch('/api/setup/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      storage_dir: wizardData.storage_dir || '~/AudioTranscriptions',
      whisper_model: wizardData.whisper_model || 'large-v3',
    }),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
}

// ── Step 5: Download ──────────────────────────────────────
document.getElementById('step5-start').addEventListener('click', startDownload);
document.getElementById('step5-finish').addEventListener('click', () => {
  sessionStorage.removeItem('wizard');
  window.location.href = '/';
});

async function startDownload() {
  const startBtn  = document.getElementById('step5-start');
  const finishBtn = document.getElementById('step5-finish');
  const errEl     = document.getElementById('dl-error');

  startBtn.disabled = true;
  startBtn.innerHTML = '<span class="spinner"></span> Downloading …';
  errEl.style.display = 'none';

  // Open WebSocket for progress
  const sessionId = Math.random().toString(36).slice(2);
  const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${wsProto}://${location.host}/ws/setup/${sessionId}`);

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.stage === 'ping') return;
    updateDownloadProgress(msg);
    if (msg.stage === 'done') {
      startBtn.style.display = 'none';
      finishBtn.style.display = '';
      document.getElementById('dl-log').textContent = '✓ All models ready!';
    }
    if (msg.stage === 'error') {
      errEl.textContent = `Error: ${msg.error}`;
      errEl.style.display = 'block';
      startBtn.disabled = false;
      startBtn.textContent = 'Retry';
    }
  };

  ws.onerror = () => {
    errEl.textContent = 'WebSocket error — check server logs.';
    errEl.style.display = 'block';
    startBtn.disabled = false;
    startBtn.textContent = 'Retry';
  };

  // Trigger download
  try {
    const res = await fetch('/api/setup/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!res.ok) throw new Error(await res.text());
  } catch (e) {
    errEl.textContent = `Failed to start download: ${e.message}`;
    errEl.style.display = 'block';
    startBtn.disabled = false;
    startBtn.textContent = 'Retry';
  }
}

function updateDownloadProgress(msg) {
  const pct = msg.pct ?? 0;
  const log = document.getElementById('dl-log');
  log.textContent = msg.message || '';

  // 0–35%: diarization models, 35–100%: whisper (matches download_models.py)
  if (pct <= 35) {
    const p = Math.round(pct / 35 * 100);
    setBar('diarization', p);
    setBar('whisper', 0);
  } else {
    setBar('diarization', 100);
    const p = Math.round((pct - 35) / 65 * 100);
    setBar('whisper', p);
  }
}

function setBar(name, pct) {
  const bar = document.getElementById(`dl-bar-${name}`);
  const pctEl = document.getElementById(`dl-pct-${name}`);
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.classList.toggle('running', pct > 0 && pct < 100);
  }
  if (pctEl) pctEl.textContent = `${pct}%`;
}
