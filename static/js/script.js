/* ===================================================================
   OverlayTranslate Server — Frontend Script
   Complete rewrite: fixes download progress, history, theme toggle,
   search, toast notifications, and status display.
   =================================================================== */

(function () {
    'use strict';

    // ─── Config ────────────────────────────────────────────────
    const MAX_INPUT_CHARS = window.APP_CONFIG?.MAX_INPUT_CHARS || 5000;
    const TRANSLATE_DEBOUNCE_MS = 500;
    const POLL_INTERVAL_MS = 1500;
    const MAX_HISTORY_ITEMS = 50;
    const TOAST_DURATION_MS = 4000;

    // ─── DOM References ────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const els = {
        // Translation
        inputText: $('#input-text'),
        outputText: $('#output-text'),
        sourceLang: $('#source-lang'),
        targetLang: $('#target-lang'),
        btnSwitch: $('#btn-switch'),
        btnClear: $('#btn-clear'),
        btnCopy: $('#btn-copy'),
        charCount: $('#char-count'),
        statusMsg: $('#status-msg'),
        spinner: $('#spinner'),
        detectedLang: $('#detected-lang'),

        // Header
        themeToggle: $('#theme-toggle'),
        btnModels: $('#btn-models'),
        modelCountBadge: $('#model-count-badge'),

        // Sidebar
        sidebar: $('#sidebar'),
        sidebarOverlay: $('#sidebar-overlay'),
        btnCloseSidebar: $('#btn-close-sidebar'),
        downloadProgress: $('#download-progress'),
        progressLabel: $('#progress-label'),
        progressPercent: $('#progress-percent'),
        progressFill: $('#progress-fill'),
        progressDetail: $('#progress-detail'),
        btnDownloadAll: $('#btn-download-all'),
        downloadAllStatus: $('#download-all-status'),
        availableModels: $('#available-models'),
        installedModels: $('#installed-models'),
        searchAvailable: $('#search-available'),
        searchInstalled: $('#search-installed'),
        availableCount: $('#available-count'),
        installedCount: $('#installed-count'),
        historyList: $('#history-list'),
        historyCount: $('#history-count'),
        btnClearHistory: $('#btn-clear-history'),

        // Diff
        diffModal: $('#diff-modal'),
        closeDiff: $('#close-diff'),
        diffView: $('#diff-view'),

        // Toast
        toastContainer: $('#toast-container'),
    };

    // ─── State ─────────────────────────────────────────────────
    let translateTimer = null;
    let availableModelsData = [];
    let installedModelsData = [];
    let activePollers = {};          // model_id → intervalId
    let downloadAllQueue = [];
    let downloadAllActive = false;
    let translationHistory = [];
    let lastTranslatedText = '';

    // ─── Init ──────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        loadTheme();
        loadHistory();
        bindEvents();
        loadLanguages();
        loadModels();
    }

    // ─── Toast Notifications ───────────────────────────────────
    function showToast(message, type = 'info') {
        if (!els.toastContainer) return;
        const icons = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-text">${escapeHTML(message)}</span>`;
        els.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('removing');
            toast.addEventListener('animationend', () => toast.remove());
        }, TOAST_DURATION_MS);
    }

    // ─── Status Message (inline in output pane) ────────────────
    function showStatus(message, type = 'info') {
        if (!els.statusMsg) return;
        els.statusMsg.className = `status-msg ${type}`;
        els.statusMsg.textContent = message;
    }

    function clearStatus() {
        if (!els.statusMsg) return;
        els.statusMsg.className = 'status-msg';
        els.statusMsg.textContent = '';
    }

    // ─── Theme Toggle ──────────────────────────────────────────
    function loadTheme() {
        const saved = localStorage.getItem('ot-theme') || 'dark';
        document.documentElement.setAttribute('data-theme', saved);
        if (els.themeToggle) els.themeToggle.checked = saved === 'light';
    }

    function toggleTheme() {
        const isLight = els.themeToggle?.checked;
        const theme = isLight ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('ot-theme', theme);
    }

    // ─── Event Bindings ────────────────────────────────────────
    function bindEvents() {
        // Translation
        els.inputText?.addEventListener('input', onInputChange);
        els.btnSwitch?.addEventListener('click', switchLanguages);
        els.btnClear?.addEventListener('click', clearInput);
        els.btnCopy?.addEventListener('click', copyOutput);
        els.sourceLang?.addEventListener('change', onLanguageChange);
        els.targetLang?.addEventListener('change', onLanguageChange);

        // Theme
        els.themeToggle?.addEventListener('change', toggleTheme);

        // Sidebar
        els.btnModels?.addEventListener('click', openSidebar);
        els.btnCloseSidebar?.addEventListener('click', closeSidebar);
        els.sidebarOverlay?.addEventListener('click', closeSidebar);

        // Download All
        els.btnDownloadAll?.addEventListener('click', downloadAll);

        // Search
        els.searchAvailable?.addEventListener('input', () => renderAvailableModels());
        els.searchInstalled?.addEventListener('input', () => renderInstalledModels());

        // History
        els.btnClearHistory?.addEventListener('click', clearHistory);

        // Diff modal
        els.closeDiff?.addEventListener('click', () => els.diffModal?.classList.remove('open'));

        // Keyboard shortcut — Escape to close sidebar / diff
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (els.diffModal?.classList.contains('open')) els.diffModal.classList.remove('open');
                else if (els.sidebar?.classList.contains('open')) closeSidebar();
            }
        });
    }

    // ─── Language Loading ──────────────────────────────────────
    async function loadLanguages() {
        try {
            const resp = await fetch('/api/languages');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const languages = data.installed || [];
            populateLangSelect(els.sourceLang, languages, true);
            populateLangSelect(els.targetLang, languages, false);
            restoreSelectedLanguages();
            highlightSameLang();
        } catch (err) {
            console.error('Failed to load languages:', err);
            showToast('Failed to load languages', 'error');
        }
    }

    function populateLangSelect(select, languages, includeAuto) {
        if (!select) return;
        select.innerHTML = '';
        if (includeAuto) {
            const opt = document.createElement('option');
            opt.value = 'auto';
            opt.textContent = 'Auto Detect';
            select.appendChild(opt);
        }
        languages.forEach(lang => {
            const opt = document.createElement('option');
            opt.value = lang.code;
            opt.textContent = `${lang.name} (${lang.code})`;
            select.appendChild(opt);
        });
    }

    function restoreSelectedLanguages() {
        const src = localStorage.getItem('ot-source-lang');
        const tgt = localStorage.getItem('ot-target-lang');
        if (src && els.sourceLang) {
            const opt = els.sourceLang.querySelector(`option[value="${src}"]`);
            if (opt) els.sourceLang.value = src;
        }
        if (tgt && els.targetLang) {
            const opt = els.targetLang.querySelector(`option[value="${tgt}"]`);
            if (opt) els.targetLang.value = tgt;
        }
    }

    function saveSelectedLanguages() {
        if (els.sourceLang) localStorage.setItem('ot-source-lang', els.sourceLang.value);
        if (els.targetLang) localStorage.setItem('ot-target-lang', els.targetLang.value);
    }

    function highlightSameLang() {
        const same = els.sourceLang?.value !== 'auto' &&
                     els.sourceLang?.value === els.targetLang?.value;
        els.sourceLang?.classList.toggle('lang-same', same);
        els.targetLang?.classList.toggle('lang-same', same);
    }

    function onLanguageChange() {
        highlightSameLang();
        saveSelectedLanguages();
        if (els.inputText?.value.trim()) {
            debouncedTranslate();
        }
    }

    function switchLanguages() {
        if (!els.sourceLang || !els.targetLang) return;
        const srcVal = els.sourceLang.value;
        const tgtVal = els.targetLang.value;
        if (srcVal === 'auto') {
            showToast('Cannot switch when source is Auto Detect', 'warning');
            return;
        }
        els.sourceLang.value = tgtVal;
        els.targetLang.value = srcVal;
        // Swap text too
        const srcText = els.inputText?.value || '';
        const tgtText = els.outputText?.value || '';
        if (els.inputText) els.inputText.value = tgtText;
        if (els.outputText) els.outputText.value = srcText;
        highlightSameLang();
        saveSelectedLanguages();
        updateCharCount();
        if (els.inputText?.value.trim()) debouncedTranslate();
    }

    // ─── Translation ───────────────────────────────────────────
    function onInputChange() {
        updateCharCount();
        debouncedTranslate();
    }

    function updateCharCount() {
        if (!els.charCount || !els.inputText) return;
        const len = els.inputText.value.length;
        els.charCount.textContent = `${len} / ${MAX_INPUT_CHARS}`;
        els.charCount.classList.toggle('over-limit', len > MAX_INPUT_CHARS);
    }

    function debouncedTranslate() {
        clearTimeout(translateTimer);
        translateTimer = setTimeout(doTranslate, TRANSLATE_DEBOUNCE_MS);
    }

    async function doTranslate() {
        const text = els.inputText?.value.trim();
        if (!text) {
            if (els.outputText) els.outputText.value = '';
            clearStatus();
            if (els.detectedLang) els.detectedLang.textContent = '';
            return;
        }
        if (text.length > MAX_INPUT_CHARS) {
            showStatus(`Text exceeds ${MAX_INPUT_CHARS} character limit`, 'error');
            return;
        }
        const srcLang = els.sourceLang?.value;
        const tgtLang = els.targetLang?.value;
        if (!srcLang || !tgtLang) return;
        if (srcLang !== 'auto' && srcLang === tgtLang) {
            if (els.outputText) els.outputText.value = text;
            showStatus('Same language selected', 'warning');
            return;
        }

        setTranslating(true);
        clearStatus();

        try {
            const resp = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, source_lang: srcLang, target_lang: tgtLang })
            });
            const data = await resp.json();

            if (!resp.ok) {
                const msg = data.message || data.error || 'Translation failed';
                showStatus(msg, 'error');
                if (data.error_code === 'LANG_NOT_INSTALLED' || data.error_code === 'MODEL_NOT_INSTALLED') {
                    showToast(`Model not installed: ${msg}`, 'warning');
                }
                return;
            }

            lastTranslatedText = data.translated_text || '';
            if (els.outputText) els.outputText.value = lastTranslatedText;
            if (data.detected_language && els.detectedLang) {
                els.detectedLang.textContent = `Detected: ${data.detected_language}`;
            } else if (els.detectedLang) {
                els.detectedLang.textContent = '';
            }
            showStatus('Translated', 'success');

            // Save to history
            addToHistory({
                source: text.substring(0, 200),
                translated: lastTranslatedText.substring(0, 200),
                srcLang: data.detected_language || srcLang,
                tgtLang,
                time: Date.now()
            });

        } catch (err) {
            console.error('Translation error:', err);
            showStatus('Connection error', 'error');
        } finally {
            setTranslating(false);
        }
    }

    function setTranslating(busy) {
        if (els.spinner) els.spinner.style.display = busy ? 'block' : 'none';
        if (els.outputText) els.outputText.style.opacity = busy ? '0.5' : '1';
    }

    function clearInput() {
        if (els.inputText) els.inputText.value = '';
        if (els.outputText) els.outputText.value = '';
        clearStatus();
        if (els.detectedLang) els.detectedLang.textContent = '';
        updateCharCount();
    }

    function copyOutput() {
        const text = els.outputText?.value;
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            if (els.btnCopy) {
                els.btnCopy.classList.add('copied');
                els.btnCopy.textContent = '✓';
                setTimeout(() => {
                    els.btnCopy.classList.remove('copied');
                    els.btnCopy.textContent = '📋';
                }, 1500);
            }
            showToast('Copied to clipboard', 'success');
        }).catch(() => {
            showToast('Copy failed', 'error');
        });
    }

    // ─── Sidebar ───────────────────────────────────────────────
    function openSidebar() {
        els.sidebar?.classList.add('open');
        els.sidebarOverlay?.classList.add('open');
        loadModels(); // Refresh on open
    }

    function closeSidebar() {
        els.sidebar?.classList.remove('open');
        els.sidebarOverlay?.classList.remove('open');
    }

    // ─── Model Management ──────────────────────────────────────
    async function loadModels() {
        try {
            const [availResp, instResp] = await Promise.all([
                fetch('/api/models/available'),
                fetch('/api/models/installed')
            ]);
            if (availResp.ok) {
                availableModelsData = await availResp.json();
            }
            if (instResp.ok) {
                installedModelsData = await instResp.json();
            }

            renderAvailableModels();
            renderInstalledModels();
            updateModelBadge();
            updateDownloadAllBtn();
        } catch (err) {
            console.error('Failed to load models:', err);
            showToast('Failed to load models', 'error');
        }
    }

    function updateModelBadge() {
        const count = availableModelsData.length;
        if (els.modelCountBadge) {
            els.modelCountBadge.textContent = count;
            els.modelCountBadge.style.display = count > 0 ? 'inline-block' : 'none';
        }
    }

    function updateDownloadAllBtn() {
        if (!els.btnDownloadAll) return;
        const count = availableModelsData.length;
        els.btnDownloadAll.disabled = count === 0 || downloadAllActive;
        els.btnDownloadAll.textContent = count > 0
            ? `Download All Available (${count})`
            : 'No Models Available';
    }

    function filterModels(models, query) {
        if (!query) return models;
        const q = query.toLowerCase();
        return models.filter(m => {
            const text = `${m.from_name || ''} ${m.to_name || ''} ${m.from_code || ''} ${m.to_code || ''} ${m.id || ''}`.toLowerCase();
            return text.includes(q);
        });
    }

    function renderAvailableModels() {
        if (!els.availableModels) return;
        const query = els.searchAvailable?.value || '';
        const filtered = filterModels(availableModelsData, query);
        if (els.availableCount) els.availableCount.textContent = filtered.length;

        if (filtered.length === 0) {
            els.availableModels.innerHTML = `<div class="empty-state">${query ? 'No matches found' : 'All models installed!'}</div>`;
            return;
        }

        els.availableModels.innerHTML = filtered.map(m => `
            <div class="model-item" data-id="${escapeAttr(m.id)}">
                <div class="model-info">
                    <div class="model-name">${escapeHTML(m.from_name)} → ${escapeHTML(m.to_name)}</div>
                    <div class="model-meta">${escapeHTML(m.id)} · v${escapeHTML(m.package_version || '?')}</div>
                </div>
                <button class="btn-model btn-download" onclick="window.__downloadModel('${escapeAttr(m.id)}')" title="Download">
                    Download
                </button>
            </div>
        `).join('');
    }

    function renderInstalledModels() {
        if (!els.installedModels) return;
        const query = els.searchInstalled?.value || '';
        const filtered = filterModels(installedModelsData, query);
        if (els.installedCount) els.installedCount.textContent = filtered.length;

        if (filtered.length === 0) {
            els.installedModels.innerHTML = `<div class="empty-state">${query ? 'No matches found' : 'No models installed'}</div>`;
            return;
        }

        els.installedModels.innerHTML = filtered.map(m => `
            <div class="model-item" data-id="${escapeAttr(m.id)}">
                <div class="model-info">
                    <div class="model-name">${escapeHTML(m.from_name)} → ${escapeHTML(m.to_name)}</div>
                    <div class="model-meta">${escapeHTML(m.id)} · v${escapeHTML(m.package_version || '?')}</div>
                </div>
                <button class="btn-model btn-delete" onclick="window.__deleteModel('${escapeAttr(m.id)}')" title="Delete">
                    Delete
                </button>
            </div>
        `).join('');
    }

    // ─── Download Model ────────────────────────────────────────
    window.__downloadModel = async function (modelId) {
        // Disable button
        const btn = els.availableModels?.querySelector(`[data-id="${modelId}"] .btn-download`);
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Queued...';
            btn.classList.add('downloading');
        }

        try {
            const resp = await fetch('/api/models/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: modelId })
            });
            const data = await resp.json();

            if (!resp.ok) {
                showToast(data.message || 'Download failed', 'error');
                if (btn) { btn.disabled = false; btn.textContent = 'Download'; btn.classList.remove('downloading'); }
                return;
            }

            showToast(`Downloading ${modelId}...`, 'info');
            showDownloadProgress(modelId);
            startPolling(modelId);

        } catch (err) {
            console.error('Download request error:', err);
            showToast('Failed to start download', 'error');
            if (btn) { btn.disabled = false; btn.textContent = 'Download'; btn.classList.remove('downloading'); }
        }
    };

    // ─── Download Progress Tracking ────────────────────────────
    function showDownloadProgress(modelId) {
        if (!els.downloadProgress) return;
        els.downloadProgress.classList.add('active');
        updateProgressUI(modelId, 0, 'Queued...', 'downloading');
    }

    function updateProgressUI(modelId, progress, message, status) {
        if (els.progressLabel) els.progressLabel.textContent = `${modelId}`;
        if (els.progressPercent) els.progressPercent.textContent = `${Math.round(progress)}%`;
        if (els.progressFill) {
            els.progressFill.style.width = `${Math.max(progress, status === 'downloading' ? 3 : 0)}%`;
            els.progressFill.className = 'progress-fill';
            if (status === 'completed') els.progressFill.classList.add('completed');
            else if (status === 'error') els.progressFill.classList.add('error');
            else if (status === 'downloading') els.progressFill.classList.add('downloading');
        }
        if (els.progressDetail) {
            els.progressDetail.textContent = message || '';
            els.progressDetail.className = 'progress-detail';
            if (status === 'completed') els.progressDetail.classList.add('success');
            else if (status === 'error') els.progressDetail.classList.add('error');
        }

        // Update button text for the specific model
        const btn = els.availableModels?.querySelector(`[data-id="${modelId}"] .btn-download`);
        if (btn) {
            if (status === 'downloading' || status === 'installing' || status === 'queued') {
                btn.disabled = true;
                btn.textContent = `${Math.round(progress)}%`;
                btn.classList.add('downloading');
            }
        }
    }

    function hideDownloadProgress(delay = 3000) {
        setTimeout(() => {
            if (els.downloadProgress) els.downloadProgress.classList.remove('active');
        }, delay);
    }

    // ─── Polling for Download Status ───────────────────────────
    function startPolling(modelId) {
        // Try SSE first, fall back to polling
        if (typeof EventSource !== 'undefined') {
            startSSE(modelId);
        } else {
            startIntervalPolling(modelId);
        }
    }

    function startSSE(modelId) {
        let es;
        try {
            es = new EventSource(`/api/download/stream/${encodeURIComponent(modelId)}`);
        } catch {
            startIntervalPolling(modelId);
            return;
        }

        let receivedData = false;
        const timeout = setTimeout(() => {
            es.close();
            console.warn('SSE timeout for', modelId);
            if (!receivedData) startIntervalPolling(modelId);
        }, 300000); // 5 min

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                // Skip the initial 'connected' heartbeat
                if (data.status === 'connected') return;
                receivedData = true;
                handleStatusUpdate(modelId, data);
                if (data.status === 'completed' || data.status === 'error' || data.status === 'not_found') {
                    clearTimeout(timeout);
                    es.close();
                }
            } catch (e) {
                console.error('SSE parse error:', e);
            }
        };

        es.onerror = () => {
            clearTimeout(timeout);
            es.close();
            console.warn('SSE error, falling back to polling for', modelId);
            startIntervalPolling(modelId);
        };
    }

    function startIntervalPolling(modelId) {
        if (activePollers[modelId]) return;
        const id = setInterval(async () => {
            try {
                const resp = await fetch(`/api/download/status/${encodeURIComponent(modelId)}`);
                if (!resp.ok) {
                    stopPolling(modelId);
                    return;
                }
                const data = await resp.json();
                handleStatusUpdate(modelId, data);
                if (data.status === 'completed' || data.status === 'error' || data.status === 'not_found') {
                    stopPolling(modelId);
                }
            } catch (err) {
                console.error('Polling error:', err);
            }
        }, POLL_INTERVAL_MS);
        activePollers[modelId] = id;
    }

    function stopPolling(modelId) {
        if (activePollers[modelId]) {
            clearInterval(activePollers[modelId]);
            delete activePollers[modelId];
        }
    }

    function handleStatusUpdate(modelId, data) {
        const progress = data.progress || 0;
        const message = data.message || '';
        const status = data.status || 'unknown';

        updateProgressUI(modelId, progress, message, status);

        if (status === 'completed') {
            showToast(`Model ${modelId} installed successfully!`, 'success');
            hideDownloadProgress();
            refreshAfterDownload();
        } else if (status === 'error') {
            showToast(`Download failed: ${message}`, 'error');
            hideDownloadProgress(5000);
            // Re-enable button
            const btn = els.availableModels?.querySelector(`[data-id="${modelId}"] .btn-download`);
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Retry';
                btn.classList.remove('downloading');
            }
        }
    }

    async function refreshAfterDownload() {
        await loadModels();
        await loadLanguages();
        // Continue download-all queue if active
        if (downloadAllActive) {
            processDownloadAllQueue();
        }
    }

    // ─── Delete Model ──────────────────────────────────────────
    window.__deleteModel = async function (modelId) {
        const btn = els.installedModels?.querySelector(`[data-id="${modelId}"] .btn-delete`);
        if (btn) { btn.disabled = true; btn.textContent = 'Deleting...'; }

        try {
            const resp = await fetch('/api/models/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: modelId })
            });
            const data = await resp.json();

            if (resp.ok) {
                showToast(`Model ${modelId} deleted`, 'success');
                await loadModels();
                await loadLanguages();
            } else {
                showToast(data.message || 'Delete failed', 'error');
                if (btn) { btn.disabled = false; btn.textContent = 'Delete'; }
            }
        } catch (err) {
            console.error('Delete error:', err);
            showToast('Failed to delete model', 'error');
            if (btn) { btn.disabled = false; btn.textContent = 'Delete'; }
        }
    };

    // ─── Download All ──────────────────────────────────────────
    async function downloadAll() {
        if (availableModelsData.length === 0 || downloadAllActive) return;
        downloadAllActive = true;
        downloadAllQueue = availableModelsData.map(m => m.id);
        updateDownloadAllBtn();
        if (els.downloadAllStatus) {
            els.downloadAllStatus.textContent = `0 / ${downloadAllQueue.length} downloaded`;
        }
        processDownloadAllQueue();
    }

    function processDownloadAllQueue() {
        if (downloadAllQueue.length === 0) {
            downloadAllActive = false;
            updateDownloadAllBtn();
            if (els.downloadAllStatus) els.downloadAllStatus.textContent = 'All downloads complete!';
            showToast('All available models downloaded!', 'success');
            return;
        }

        const total = availableModelsData.length;
        const remaining = downloadAllQueue.length;
        const done = total - remaining;
        if (els.downloadAllStatus) {
            els.downloadAllStatus.textContent = `${done} / ${total} downloaded`;
        }

        const nextId = downloadAllQueue.shift();
        window.__downloadModel(nextId);
    }

    // ─── Translation History ───────────────────────────────────
    function loadHistory() {
        try {
            const raw = localStorage.getItem('ot-history');
            translationHistory = raw ? JSON.parse(raw) : [];
        } catch {
            translationHistory = [];
        }
        renderHistory();
    }

    function saveHistory() {
        try {
            localStorage.setItem('ot-history', JSON.stringify(translationHistory));
        } catch {
            // Quota exceeded — trim older entries
            translationHistory = translationHistory.slice(0, MAX_HISTORY_ITEMS / 2);
            try { localStorage.setItem('ot-history', JSON.stringify(translationHistory)); } catch { /* give up */ }
        }
    }

    function addToHistory(entry) {
        // Deduplicate
        translationHistory = translationHistory.filter(
            h => !(h.source === entry.source && h.srcLang === entry.srcLang && h.tgtLang === entry.tgtLang)
        );
        translationHistory.unshift(entry);
        if (translationHistory.length > MAX_HISTORY_ITEMS) {
            translationHistory = translationHistory.slice(0, MAX_HISTORY_ITEMS);
        }
        saveHistory();
        renderHistory();
    }

    function renderHistory() {
        if (!els.historyList) return;
        if (els.historyCount) els.historyCount.textContent = translationHistory.length;

        if (translationHistory.length === 0) {
            els.historyList.innerHTML = '<div class="empty-state">No translations yet</div>';
            return;
        }

        els.historyList.innerHTML = translationHistory.map((h, i) => {
            const timeStr = new Date(h.time).toLocaleString(undefined, {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            });
            return `
                <div class="history-item" onclick="window.__loadHistory(${i})" title="${escapeAttr(h.source)}">
                    <div class="hist-text">${escapeHTML(h.source)}</div>
                    <div class="hist-meta">${escapeHTML(String(h.srcLang))} → ${escapeHTML(String(h.tgtLang))} · ${timeStr}</div>
                </div>
            `;
        }).join('');
    }

    window.__loadHistory = function (index) {
        const entry = translationHistory[index];
        if (!entry) return;
        if (els.inputText) els.inputText.value = entry.source;
        if (els.outputText) els.outputText.value = entry.translated || '';
        updateCharCount();
        closeSidebar();
    };

    function clearHistory() {
        translationHistory = [];
        saveHistory();
        renderHistory();
        showToast('History cleared', 'info');
    }

    // ─── Utility Functions ─────────────────────────────────────
    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeAttr(str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

})();
