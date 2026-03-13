const API_BASE = window.location.origin + '/api';

let workflows = [];
let logs = [];
let currentSection = 'workflows';
let editingWorkflowId = null;
let editorSteps = [];
let initialEditorState = null;

// Filter/sort state
let workflowSearch = '';
let workflowFilter = 'all';
let workflowSort = 'name-asc';
let logStatusFilter = 'all';
let logSearchQuery = '';
let logDateFilter = 'all';
let logDisplayCount = 50;

// Auto-refresh
let logRefreshCountdown = 15;
let logRefreshInterval = null;
let logCountdownInterval = null;

// Health check
let healthCheckInterval = 30000;
let isServerConnected = true;

const ACTION_OPTIONS = [
    { value: 'open_app', label: 'Open Application', icon: '🚀' },
    { value: 'open_url', label: 'Open URL', icon: '🌐' },
    { value: 'run_command', label: 'Run Command', icon: '⚡' },
    { value: 'notify', label: 'Send Notification', icon: '🔔' },
    { value: 'calendar_check', label: 'Check Calendar', icon: '📅' },
    { value: 'conditional', label: 'Conditional', icon: '🔀' },
];

const ACTION_PARAMS = {
    open_app: [
        { key: 'command', label: 'Application Command', placeholder: 'e.g., pycharm, code, firefox', required: true },
        { key: 'args', label: 'Arguments (comma-separated)', placeholder: 'e.g., --new-window, /path/to/project' },
    ],
    open_url: [
        { key: 'url', label: 'URL', placeholder: 'https://example.com', required: true },
    ],
    run_command: [
        { key: 'command', label: 'Shell Command', placeholder: 'e.g., echo "Hello"', required: true },
        { key: 'timeout', label: 'Timeout (seconds)', placeholder: '60' },
        { key: 'cwd', label: 'Working Directory', placeholder: '/home/user/project' },
        { key: 'env_from_pycharm', label: 'PyCharm Env (optional)', placeholder: '~/Projects/myapp::CONFIG NAME' },
        { key: 'background', label: 'Run in Background', placeholder: 'true / false' },
    ],
    notify: [
        { key: 'title', label: 'Title', placeholder: 'Notification title', required: true },
        { key: 'message', label: 'Message', placeholder: 'Notification body' },
        { key: 'urgency', label: 'Urgency', placeholder: 'low / normal / critical' },
    ],
    calendar_check: [
        { key: 'calendar_id', label: 'Calendar ID', placeholder: 'primary' },
        { key: 'lookahead_hours', label: 'Lookahead (hours)', placeholder: '24' },
    ],
    conditional: [
        { key: 'condition', label: 'Condition', placeholder: 'e.g., has_events, event_count > 0', required: true },
    ],
};

const WORKFLOW_TEMPLATES = [
    { name: 'Morning Routine', icon: '☀️', description: 'Open apps and sites for your morning', steps: [
        { action: 'open_app', params: { command: 'firefox' } },
        { action: 'open_url', params: { url: 'https://mail.google.com' } },
        { action: 'notify', params: { title: 'Good Morning!', message: 'Your workspace is ready.' } },
    ]},
    { name: 'Dev Setup', icon: '💻', description: 'Launch your development environment', steps: [
        { action: 'open_app', params: { command: 'code' } },
        { action: 'run_command', params: { command: 'cd ~/project && git pull', timeout: 30 } },
        { action: 'open_url', params: { url: 'http://localhost:3000' } },
    ]},
    { name: 'Backup Script', icon: '💾', description: 'Run backup commands', steps: [
        { action: 'run_command', params: { command: 'tar -czf ~/backup.tar.gz ~/Documents', timeout: 120 } },
        { action: 'notify', params: { title: 'Backup Complete', message: 'Your files have been backed up.' } },
    ]},
    { name: 'System Health Check', icon: '🩺', description: 'Check system resource usage', steps: [
        { action: 'run_command', params: { command: 'df -h && free -m', timeout: 10 } },
        { action: 'run_command', params: { command: 'uptime', timeout: 5 } },
        { action: 'notify', params: { title: 'Health Check Done', message: 'System status logged.' } },
    ]},
];

// ---- Utilities ----
function esc(text) {
    const d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
}

function formatTime(iso) {
    try {
        const d = new Date(iso);
        const diff = Date.now() - d;
        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
}

function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function animateCountUp(el, target) {
    const start = parseInt(el.textContent) || 0;
    if (start === target) return;
    const duration = 400;
    const startTime = performance.now();
    function update(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (target - start) * eased);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ---- Toast ----
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✓', error: '✗', info: 'i' };
    toast.innerHTML = `<span class="toast-icon toast-icon-${type}">${icons[type] || 'i'}</span><span>${esc(message)}</span><div class="toast-progress" style="width:100%;transition:width 4s linear;"></div>`;
    container.appendChild(toast);
    // Start progress bar shrink
    requestAnimationFrame(() => {
        const bar = toast.querySelector('.toast-progress');
        if (bar) bar.style.width = '0%';
    });
    // Click to dismiss
    toast.addEventListener('click', () => { toast.classList.add('hiding'); setTimeout(() => toast.remove(), 200); });
    setTimeout(() => { toast.classList.add('hiding'); setTimeout(() => toast.remove(), 200); }, 4000);
}

// ---- Confirm Modal ----
let confirmCallback = null;
function showConfirmModal(title, message, confirmText, onConfirm, isDanger = true) {
    const modal = document.getElementById('confirm-modal');
    document.getElementById('confirm-modal-title').textContent = title;
    document.getElementById('confirm-modal-message').textContent = message;
    document.getElementById('confirm-modal-confirm').textContent = confirmText;
    const icon = document.getElementById('confirm-modal-icon');
    icon.className = `confirm-modal-icon ${isDanger ? 'danger' : 'warning'}`;
    confirmCallback = onConfirm;
    modal.style.display = 'flex';
    document.getElementById('confirm-modal-cancel').focus();
    trapFocus(modal);
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
    confirmCallback = null;
}

// ---- Focus Trap ----
function trapFocus(el) {
    const focusable = el.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    el._trapHandler = (e) => {
        if (e.key !== 'Tab') return;
        if (e.shiftKey) { if (document.activeElement === first) { e.preventDefault(); last.focus(); } }
        else { if (document.activeElement === last) { e.preventDefault(); first.focus(); } }
    };
    el.addEventListener('keydown', el._trapHandler);
}

// ---- API ----
async function apiFetch(path, options = {}) {
    try {
        const res = await fetch(API_BASE + path, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        return await res.json();
    } catch (e) {
        if (e.message.includes('Failed to fetch')) {
            showToast('Cannot connect to AutoFlow server', 'error');
        }
        throw e;
    }
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initEditor();
    initAIEditor();
    initCustomSelects();
    initWorkflowFilters();
    initLogFilters();
    initSettings();
    initAISettings();
    initTemplates();
    initConfirmModal();
    initKeyboardShortcuts();

    showSkeletons();
    loadWorkflows().then(hideSkeletons);
    loadLogs();
    checkServerHealth();
    startHealthCheckLoop();
    startLogRefreshLoop();

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.custom-select')) {
            document.querySelectorAll('.custom-select.open').forEach(s => {
                s.classList.remove('open');
                const dd = s.querySelector('.custom-select-dropdown');
                if (dd) { dd.style.removeProperty('bottom'); dd.style.removeProperty('top'); dd.classList.remove('flip-up'); }
            });
        }
        if (!e.target.closest('.cron-helper-wrapper')) {
            const ch = document.getElementById('cron-helper');
            if (ch) ch.classList.remove('visible');
        }
    });
});

function showSkeletons() {
    const ss = document.getElementById('stats-skeleton');
    const ws = document.getElementById('workflows-skeleton');
    const ls = document.getElementById('logs-skeleton');
    if (ss) ss.style.display = '';
    if (ws) ws.style.display = '';
    if (ls) ls.style.display = '';
    document.getElementById('stats-grid').style.display = 'none';
    document.getElementById('workflow-search-bar').style.display = 'none';
}

function hideSkeletons() {
    const ss = document.getElementById('stats-skeleton');
    const ws = document.getElementById('workflows-skeleton');
    const ls = document.getElementById('logs-skeleton');
    if (ss) ss.style.display = 'none';
    if (ws) ws.style.display = 'none';
    if (ls) ls.style.display = 'none';
    const sg = document.getElementById('stats-grid');
    const sb = document.getElementById('workflow-search-bar');
    sg.style.display = '';
    sb.style.display = '';
    sg.classList.add('content-fade-in');
    sb.classList.add('content-fade-in');
}

// ---- Custom Select ----
function initCustomSelects() {
    document.querySelectorAll('.custom-select').forEach(setupCustomSelect);
}

function setupCustomSelect(el) {
    const trigger = el.querySelector('.custom-select-trigger');
    const dropdown = el.querySelector('.custom-select-dropdown');
    const options = () => Array.from(el.querySelectorAll('.custom-select-option'));
    let highlightIdx = -1;
    el.setAttribute('tabindex', '0');

    function openDropdown() {
        document.querySelectorAll('.custom-select.open').forEach(s => { if (s !== el) closeDropdown(s); });
        dropdown.style.removeProperty('bottom');
        dropdown.style.removeProperty('top');
        dropdown.style.removeProperty('margin-bottom');
        dropdown.classList.remove('flip-up');
        const triggerRect = trigger.getBoundingClientRect();
        const spaceBelow = window.innerHeight - triggerRect.bottom;
        const dropdownHeight = Math.min(options().length * 40 + 8, 260);
        if (spaceBelow < dropdownHeight + 12 && triggerRect.top > dropdownHeight) {
            dropdown.classList.add('flip-up');
            dropdown.style.bottom = '100%';
            dropdown.style.top = 'auto';
            dropdown.style.marginBottom = '6px';
        }
        el.classList.add('open');
        el.setAttribute('aria-expanded', 'true');
        const opts = options();
        highlightIdx = opts.findIndex(o => o.classList.contains('selected'));
        if (highlightIdx < 0) highlightIdx = 0;
        updateHighlight(opts);
        el.focus();
    }

    function closeDropdown(target) {
        const t = target || el;
        t.classList.remove('open');
        t.setAttribute('aria-expanded', 'false');
        const dd = t.querySelector('.custom-select-dropdown');
        if (dd) { dd.style.removeProperty('bottom'); dd.style.removeProperty('top'); dd.style.removeProperty('margin-bottom'); dd.classList.remove('flip-up'); }
    }

    function selectOption(opt) {
        const value = opt.dataset.value;
        const labelEl = opt.querySelector('span:not(.action-option-icon)') || opt.querySelector('span');
        const label = labelEl ? labelEl.textContent : opt.textContent.trim();
        el.dataset.value = value;
        const iconEl = opt.querySelector('.action-option-icon');
        const triggerIcon = el.querySelector('.custom-select-trigger .action-option-icon');
        if (iconEl && triggerIcon) triggerIcon.textContent = iconEl.textContent;
        el.querySelector('.custom-select-value').textContent = label;
        options().forEach(o => o.classList.remove('selected', 'highlighted'));
        opt.classList.add('selected');
        closeDropdown();
        el.dispatchEvent(new CustomEvent('change', { detail: { value } }));
    }

    function updateHighlight(opts) {
        opts.forEach((o, i) => o.classList.toggle('highlighted', i === highlightIdx));
        if (highlightIdx >= 0 && opts[highlightIdx]) opts[highlightIdx].scrollIntoView({ block: 'nearest' });
    }

    trigger.addEventListener('click', (e) => { e.stopPropagation(); if (el.classList.contains('open')) closeDropdown(); else openDropdown(); });
    dropdown.addEventListener('click', (e) => { e.stopPropagation(); const opt = e.target.closest('.custom-select-option'); if (opt) selectOption(opt); });

    el.addEventListener('keydown', (e) => {
        if (!el.classList.contains('open')) {
            if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); e.stopPropagation(); openDropdown(); }
            return;
        }
        const opts = options();
        e.preventDefault(); e.stopPropagation();
        switch (e.key) {
            case 'ArrowDown': highlightIdx = Math.min(highlightIdx + 1, opts.length - 1); updateHighlight(opts); break;
            case 'ArrowUp': highlightIdx = Math.max(highlightIdx - 1, 0); updateHighlight(opts); break;
            case 'Enter': case ' ': if (highlightIdx >= 0 && opts[highlightIdx]) selectOption(opts[highlightIdx]); break;
            case 'Escape': case 'Tab': closeDropdown(); break;
        }
    });
}

function createActionSelect(stepIndex, currentAction) {
    const current = ACTION_OPTIONS.find(a => a.value === currentAction) || ACTION_OPTIONS[0];
    const optionsHtml = ACTION_OPTIONS.map(a => `
        <div class="custom-select-option ${a.value === currentAction ? 'selected' : ''}" data-value="${a.value}" role="option">
            <span class="action-option-icon">${a.icon}</span>
            <span>${a.label}</span>
        </div>
    `).join('');
    return `
        <div class="custom-select action-select" data-value="${currentAction}" data-step-index="${stepIndex}" role="listbox">
            <div class="custom-select-trigger">
                <span class="action-option-icon">${current.icon}</span>
                <span class="custom-select-value">${current.label}</span>
                <svg class="custom-select-arrow" width="12" height="12" viewBox="0 0 12 8" fill="none"><path d="M1 1.5L6 6.5L11 1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </div>
            <div class="custom-select-dropdown">${optionsHtml}</div>
        </div>
    `;
}

// ---- Navigation ----
function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const section = item.dataset.section;
            if (currentSection === 'editor' && section !== 'editor' && isEditorDirty()) {
                showConfirmModal('Unsaved Changes', 'You have unsaved changes. Discard them?', 'Discard', () => {
                    closeConfirmModal();
                    switchSection(section);
                }, false);
                return;
            }
            switchSection(section);
        });
    });
}

function switchSection(section) {
    // Fade out current
    const currentEl = document.getElementById(`section-${currentSection}`);
    if (currentEl && currentSection !== section) {
        currentEl.classList.add('fade-out');
        setTimeout(() => { currentEl.classList.add('hidden'); currentEl.classList.remove('fade-out'); }, 150);
    }

    currentSection = section;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`[data-section="${section}"]`)?.classList.add('active');

    setTimeout(() => {
        document.querySelectorAll('.section').forEach(s => { if (s.id !== `section-${section}`) s.classList.add('hidden'); });
        document.getElementById(`section-${section}`)?.classList.remove('hidden');
    }, currentEl && currentEl.id !== `section-${section}` ? 150 : 0);

    const titles = {
        workflows: ['Workflows', 'Manage your automated workflows'],
        editor: ['Workflow Editor', 'Configure workflow steps and triggers'],
        logs: ['Execution Logs', 'Monitor workflow execution history'],
        settings: ['Settings', 'Configure AutoFlow preferences'],
    };
    const [title, subtitle] = titles[section] || ['', ''];
    document.getElementById('page-title').textContent = title;
    document.getElementById('page-subtitle').textContent = subtitle;
    document.getElementById('page-title').focus();

    const createBtn = document.getElementById('btn-create-workflow');
    createBtn.style.display = section === 'workflows' ? 'inline-flex' : 'none';

    if (section === 'workflows') loadWorkflows();
    if (section === 'logs') loadLogs();
}

// ---- Workflow Filters ----
function initWorkflowFilters() {
    const searchInput = document.getElementById('workflow-search');
    const clearBtn = document.getElementById('workflow-search-clear');
    const debouncedRender = debounce(() => renderWorkflows(), 250);

    searchInput.addEventListener('input', () => {
        workflowSearch = searchInput.value.trim().toLowerCase();
        clearBtn.style.display = workflowSearch ? 'flex' : 'none';
        debouncedRender();
    });
    clearBtn.addEventListener('click', () => {
        searchInput.value = ''; workflowSearch = ''; clearBtn.style.display = 'none'; renderWorkflows();
    });

    document.getElementById('workflow-filters').addEventListener('click', (e) => {
        const pill = e.target.closest('.filter-pill');
        if (!pill) return;
        document.querySelectorAll('#workflow-filters .filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        workflowFilter = pill.dataset.filter;
        renderWorkflows();
    });

    const sortSelect = document.getElementById('workflow-sort-select');
    setupCustomSelect(sortSelect);
    sortSelect.addEventListener('change', (e) => { workflowSort = e.detail.value; renderWorkflows(); });
}

function getFilteredWorkflows() {
    let filtered = [...workflows];
    if (workflowSearch) {
        filtered = filtered.filter(w => w.name.toLowerCase().includes(workflowSearch) || (w.description || '').toLowerCase().includes(workflowSearch));
    }
    if (workflowFilter === 'active') filtered = filtered.filter(w => w.enabled);
    else if (workflowFilter === 'inactive') filtered = filtered.filter(w => !w.enabled);
    else if (['manual', 'cron', 'interval', 'login'].includes(workflowFilter)) filtered = filtered.filter(w => w.trigger_type === workflowFilter);

    switch (workflowSort) {
        case 'name-asc': filtered.sort((a, b) => a.name.localeCompare(b.name)); break;
        case 'name-desc': filtered.sort((a, b) => b.name.localeCompare(a.name)); break;
        case 'newest': filtered.sort((a, b) => (b.id || 0) - (a.id || 0)); break;
        case 'oldest': filtered.sort((a, b) => (a.id || 0) - (b.id || 0)); break;
    }
    return filtered;
}

// ---- Workflows ----
async function loadWorkflows() {
    try {
        const data = await apiFetch('/workflows');
        workflows = data.workflows || [];
        renderWorkflows();
        updateStats();
    } catch (e) { console.error('Failed to load workflows:', e); }
}

function renderWorkflows() {
    const list = document.getElementById('workflows-list');
    const empty = document.getElementById('empty-state');
    const filtered = getFilteredWorkflows();

    if (workflows.length === 0) {
        list.style.display = 'none'; empty.style.display = 'flex'; return;
    }
    if (filtered.length === 0) {
        list.innerHTML = '<div class="empty-state" style="padding:30px;"><p>No workflows match your filters</p></div>';
        list.style.display = 'flex'; empty.style.display = 'none'; return;
    }

    list.style.display = 'flex'; empty.style.display = 'none';
    list.innerHTML = filtered.map(wf => `
        <div class="workflow-card ${wf.enabled ? 'card-active' : ''}" onclick="editWorkflow(${wf.id})">
            <div class="workflow-status-indicator ${wf.enabled ? 'active' : 'inactive'}"></div>
            <div class="workflow-info">
                <div class="workflow-name">${esc(wf.name)}</div>
                <div class="workflow-desc">${esc(wf.description || 'No description')}</div>
            </div>
            <div class="workflow-meta">
                <span class="workflow-badge badge-${wf.trigger_type}">${wf.trigger_type}</span>
                <span class="workflow-step-count">${countSteps(wf)} steps</span>
            </div>
            <div class="workflow-actions" onclick="event.stopPropagation()">
                <button class="btn-icon edit" title="Edit" aria-label="Edit workflow" onclick="editWorkflow(${wf.id})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                </button>
                <button class="btn-icon play" title="Run now" aria-label="Run workflow" onclick="runWorkflow(${wf.id}, '${esc(wf.name)}', this)">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                </button>
                <button class="btn-icon" title="Toggle" aria-label="Toggle workflow" onclick="toggleWorkflow(${wf.id}, this)">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 11-3.19-2.13"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                </button>
                <button class="btn-icon delete" title="Delete" aria-label="Delete workflow" onclick="deleteWorkflow(${wf.id}, '${esc(wf.name)}')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                </button>
            </div>
        </div>
    `).join('');
}

function countSteps(wf) { return (wf.definition?.steps || []).length; }

function updateStats() {
    animateCountUp(document.getElementById('stat-total'), workflows.length);
    animateCountUp(document.getElementById('stat-active'), workflows.filter(w => w.enabled).length);
    animateCountUp(document.getElementById('stat-scheduled'), workflows.filter(w => w.trigger_type !== 'manual').length);
    const today = new Date().toISOString().split('T')[0];
    animateCountUp(document.getElementById('stat-runs'), logs.filter(l => l.started_at?.startsWith(today)).length);
}

async function runWorkflow(id, name, btn) {
    if (btn) { btn.classList.add('btn-loading'); btn.disabled = true; }
    try {
        await apiFetch(`/workflows/${id}/run`, { method: 'POST' });
        showToast(`Started "${name}"`, 'success');
        setTimeout(loadLogs, 2000);
    } catch (e) { showToast(`Failed to run: ${e.message}`, 'error'); }
    finally { if (btn) { btn.classList.remove('btn-loading'); btn.disabled = false; } }
}

async function toggleWorkflow(id, btn) {
    // Optimistic UI
    const wf = workflows.find(w => w.id === id);
    if (wf) {
        wf.enabled = !wf.enabled;
        renderWorkflows();
        updateStats();
    }
    try {
        const r = await apiFetch(`/workflows/${id}/toggle`, { method: 'POST' });
        showToast(`${r.name} ${r.enabled ? 'enabled' : 'disabled'}`, 'info');
        // Sync with server state
        if (wf) wf.enabled = r.enabled;
        renderWorkflows();
        updateStats();
    } catch (e) {
        // Revert
        if (wf) { wf.enabled = !wf.enabled; renderWorkflows(); updateStats(); }
        showToast(`Failed: ${e.message}`, 'error');
    }
}

async function deleteWorkflow(id, name) {
    showConfirmModal('Delete Workflow', `Are you sure you want to delete "${name}"? This action cannot be undone.`, 'Delete', async () => {
        closeConfirmModal();
        try {
            await apiFetch(`/workflows/${id}`, { method: 'DELETE' });
            showToast(`Deleted "${name}"`, 'info');
            loadWorkflows();
        } catch (e) { showToast(`Failed: ${e.message}`, 'error'); }
    });
}

// ---- Editor ----
function initEditor() {
    document.getElementById('btn-create-workflow').addEventListener('click', showCreateModal);
    document.getElementById('btn-editor-cancel').addEventListener('click', () => {
        if (isEditorDirty()) {
            showConfirmModal('Unsaved Changes', 'You have unsaved changes. Discard them?', 'Discard', () => { closeConfirmModal(); switchSection('workflows'); }, false);
        } else { switchSection('workflows'); }
    });
    document.getElementById('btn-editor-save').addEventListener('click', saveWorkflow);
    document.getElementById('btn-add-step').addEventListener('click', addStep);

    // Trigger type change with slide animation
    const triggerSelect = document.getElementById('wf-trigger-select');
    triggerSelect.addEventListener('change', (e) => {
        const val = e.detail.value;
        const cfg = document.getElementById('trigger-config-group');
        const label = document.getElementById('trigger-config-label');
        const input = document.getElementById('wf-trigger-config');
        if (val === 'cron') {
            cfg.classList.add('open'); label.innerHTML = 'Cron Expression <span class="required-asterisk">*</span>'; input.placeholder = '0 9 * * * (every day at 9 AM)';
        } else if (val === 'interval') {
            cfg.classList.add('open'); label.innerHTML = 'Interval (minutes) <span class="required-asterisk">*</span>'; input.placeholder = '30';
        } else { cfg.classList.remove('open'); }
    });

    // Cron helper
    const cronInput = document.getElementById('wf-trigger-config');
    cronInput.addEventListener('focus', () => {
        if (document.getElementById('wf-trigger-select').dataset.value === 'cron') {
            document.getElementById('cron-helper').classList.add('visible');
        }
    });
    document.getElementById('cron-helper').addEventListener('click', (e) => {
        const ex = e.target.closest('.cron-example');
        if (ex) { cronInput.value = ex.dataset.cron; document.getElementById('cron-helper').classList.remove('visible'); cronInput.focus(); }
    });

    // Clear validation on input
    document.getElementById('wf-name').addEventListener('input', function() {
        this.classList.remove('invalid');
        document.getElementById('wf-name-error').classList.remove('visible');
    });
    cronInput.addEventListener('input', function() {
        this.classList.remove('invalid');
        document.getElementById('wf-cron-error').classList.remove('visible');
    });
}

function getEditorSnapshot() {
    return JSON.stringify({
        name: document.getElementById('wf-name').value,
        desc: document.getElementById('wf-description').value,
        trigger: document.getElementById('wf-trigger-select').dataset.value,
        triggerCfg: document.getElementById('wf-trigger-config').value,
        steps: editorSteps,
    });
}

function isEditorDirty() {
    if (!initialEditorState) return false;
    return getEditorSnapshot() !== initialEditorState;
}

function showCreateModal() {
    editingWorkflowId = null;
    editorSteps = [];
    document.getElementById('editor-title').textContent = 'New Workflow';
    document.getElementById('wf-name').value = '';
    document.getElementById('wf-description').value = '';
    setCustomSelectValue('wf-trigger-select', 'manual', 'Manual');
    document.getElementById('trigger-config-group').classList.remove('open');
    document.getElementById('wf-trigger-config').value = '';
    
    // Reset to Manual tab
    const manualTab = document.querySelector('#editor-tabs .filter-pill[data-tab="manual"]');
    if (manualTab) manualTab.click();
    
    clearValidation();
    renderSteps();
    switchSection('editor');
    initialEditorState = getEditorSnapshot();
}

function setCustomSelectValue(id, value, label) {
    const el = document.getElementById(id);
    if (!el) return;
    el.dataset.value = value;
    el.querySelector('.custom-select-value').textContent = label;
    el.querySelectorAll('.custom-select-option').forEach(o => o.classList.toggle('selected', o.dataset.value === value));
}

function editWorkflow(id) {
    const wf = workflows.find(w => w.id === id);
    if (!wf) return;
    editingWorkflowId = id;
    const def = wf.definition || {};
    editorSteps = (def.steps || []).map(s => ({ ...s }));
    document.getElementById('editor-title').textContent = `Edit: ${wf.name}`;
    document.getElementById('wf-name').value = wf.name;
    document.getElementById('wf-description').value = wf.description || '';
    const triggerLabels = { manual: 'Manual', login: 'On Login', cron: 'Cron Schedule', interval: 'Interval' };
    setCustomSelectValue('wf-trigger-select', wf.trigger_type, triggerLabels[wf.trigger_type] || wf.trigger_type);
    const cfg = wf.trigger_config || {};
    const tcg = document.getElementById('trigger-config-group');
    if (wf.trigger_type === 'cron') {
        tcg.classList.add('open'); document.getElementById('trigger-config-label').innerHTML = 'Cron Expression <span class="required-asterisk">*</span>'; document.getElementById('wf-trigger-config').value = cfg.cron || '';
    } else if (wf.trigger_type === 'interval') {
        tcg.classList.add('open'); document.getElementById('trigger-config-label').innerHTML = 'Interval (minutes) <span class="required-asterisk">*</span>'; document.getElementById('wf-trigger-config').value = cfg.interval_minutes || '';
    } else { tcg.classList.remove('open'); }
    clearValidation();
    renderSteps();
    switchSection('editor');
    initialEditorState = getEditorSnapshot();
}

function addStep() {
    editorSteps.push({ action: 'open_app', params: {} });
    renderSteps();
    const list = document.getElementById('steps-list');
    setTimeout(() => list.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
}

function removeStep(index) { editorSteps.splice(index, 1); renderSteps(); }

function duplicateStep(index) {
    const clone = JSON.parse(JSON.stringify(editorSteps[index]));
    editorSteps.splice(index + 1, 0, clone);
    renderSteps();
}

function moveStep(index, direction) {
    const newIdx = index + direction;
    if (newIdx < 0 || newIdx >= editorSteps.length) return;
    [editorSteps[index], editorSteps[newIdx]] = [editorSteps[newIdx], editorSteps[index]];
    renderSteps();
}

function renderSteps() {
    const list = document.getElementById('steps-list');
    if (editorSteps.length === 0) {
        list.innerHTML = `<div class="steps-empty"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg><p>No steps yet — click "Add Step" to get started</p></div>`;
        return;
    }
    list.innerHTML = editorSteps.map((step, i) => {
        const paramDefs = ACTION_PARAMS[step.action] || [];
        const paramsHtml = paramDefs.map(p => `
            <div class="step-param">
                <label class="step-param-label">${p.label}${p.required ? ' <span class="required-asterisk">*</span>' : ''}</label>
                <input type="text" value="${esc(getStepParam(step, p.key))}" placeholder="${p.placeholder || ''}" onchange="updateStepParam(${i}, '${p.key}', this.value)" class="step-param-input" data-param-key="${p.key}" data-step-index="${i}" ${p.required ? 'required' : ''}>
            </div>
        `).join('');
        return `
            <div class="step-card" data-step="${i}" draggable="true">
                <div class="drag-handle" title="Drag to reorder">⠿</div>
                <div class="step-number">${i + 1}</div>
                <div class="step-content">
                    ${createActionSelect(i, step.action)}
                    <div class="step-params">${paramsHtml}</div>
                </div>
                <div class="step-actions">
                    <button class="step-action-btn" onclick="moveStep(${i}, -1)" title="Move up" aria-label="Move step up" ${i === 0 ? 'disabled' : ''}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18,15 12,9 6,15"/></svg>
                    </button>
                    <button class="step-action-btn" onclick="moveStep(${i}, 1)" title="Move down" aria-label="Move step down" ${i === editorSteps.length - 1 ? 'disabled' : ''}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6,9 12,15 18,9"/></svg>
                    </button>
                    <button class="step-action-btn" onclick="duplicateStep(${i})" title="Duplicate step" aria-label="Duplicate step">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                    </button>
                    <button class="step-action-btn delete-step" onclick="removeStep(${i})" title="Remove step" aria-label="Remove step">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    // Bind action selects and drag-and-drop
    list.querySelectorAll('.action-select').forEach(el => {
        setupCustomSelect(el);
        el.addEventListener('change', (e) => { const idx = parseInt(el.dataset.stepIndex); editorSteps[idx].action = e.detail.value; editorSteps[idx].params = {}; renderSteps(); });
    });
    initStepDragDrop();
}

function initStepDragDrop() {
    const cards = document.querySelectorAll('.step-card[draggable]');
    cards.forEach(card => {
        card.addEventListener('dragstart', (e) => { card.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', card.dataset.step); });
        card.addEventListener('dragend', () => { card.classList.remove('dragging'); document.querySelectorAll('.step-card.drag-over').forEach(c => c.classList.remove('drag-over')); });
        card.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; card.classList.add('drag-over'); });
        card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
        card.addEventListener('drop', (e) => {
            e.preventDefault(); card.classList.remove('drag-over');
            const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
            const toIdx = parseInt(card.dataset.step);
            if (fromIdx !== toIdx) { const [moved] = editorSteps.splice(fromIdx, 1); editorSteps.splice(toIdx, 0, moved); renderSteps(); }
        });
    });
}

function getStepParam(step, key) {
    if (key === 'args' && Array.isArray(step.params?.[key])) return step.params[key].join(', ');
    return step.params?.[key] ?? '';
}

function updateStepParam(idx, key, value) {
    if (!editorSteps[idx].params) editorSteps[idx].params = {};
    if (key === 'args') { editorSteps[idx].params[key] = value.split(',').map(s => s.trim()).filter(Boolean); }
    else if (['timeout', 'lookahead_hours'].includes(key)) { editorSteps[idx].params[key] = value ? parseInt(value) : undefined; }
    else if (key === 'condition') { editorSteps[idx].condition = value; }
    else { editorSteps[idx].params[key] = value || undefined; }
}

// ---- Validation ----
function clearValidation() {
    document.querySelectorAll('.form-input.invalid, .step-param-input.invalid').forEach(el => el.classList.remove('invalid'));
    document.querySelectorAll('.form-error.visible').forEach(el => el.classList.remove('visible'));
}

function validateEditor() {
    clearValidation();
    let valid = true;
    const nameInput = document.getElementById('wf-name');
    if (!nameInput.value.trim()) {
        nameInput.classList.add('invalid');
        document.getElementById('wf-name-error').classList.add('visible');
        valid = false;
    }
    const triggerType = document.getElementById('wf-trigger-select').dataset.value;
    const cronInput = document.getElementById('wf-trigger-config');
    if (triggerType === 'cron' && cronInput.value.trim()) {
        const cronRegex = /^(\S+\s+){4}\S+$/;
        if (!cronRegex.test(cronInput.value.trim())) {
            cronInput.classList.add('invalid');
            document.getElementById('wf-cron-error').classList.add('visible');
            valid = false;
        }
    }
    // Required step params
    document.querySelectorAll('.step-param-input[required]').forEach(input => {
        if (!input.value.trim()) { input.classList.add('invalid'); valid = false; }
    });
    return valid;
}

async function saveWorkflow() {
    if (!validateEditor()) return;
    const saveBtn = document.getElementById('btn-editor-save');
    saveBtn.classList.add('btn-loading');
    saveBtn.innerHTML = '<span class="btn-spinner"></span><span class="btn-label">Saving...</span>';
    saveBtn.disabled = true;

    const name = document.getElementById('wf-name').value.trim();
    const triggerType = document.getElementById('wf-trigger-select').dataset.value;
    const triggerConfigInput = document.getElementById('wf-trigger-config').value.trim();
    let triggerConfig = {};
    if (triggerType === 'cron') triggerConfig = { cron: triggerConfigInput };
    if (triggerType === 'interval') triggerConfig = { interval_minutes: parseInt(triggerConfigInput) || 30 };

    const cleanSteps = editorSteps.map(step => {
        const clean = { action: step.action, params: {} };
        if (step.params) { for (const [k, v] of Object.entries(step.params)) { if (v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)) clean.params[k] = v; } }
        if (step.condition) clean.condition = step.condition;
        return clean;
    });

    const body = {
        name, description: document.getElementById('wf-description').value.trim(),
        definition: { name, description: document.getElementById('wf-description').value.trim(), trigger: { type: triggerType, ...triggerConfig }, steps: cleanSteps },
        trigger_type: triggerType, trigger_config: triggerConfig,
    };

    try {
        if (editingWorkflowId) {
            await apiFetch(`/workflows/${editingWorkflowId}`, { method: 'PUT', body: JSON.stringify(body) });
            showToast(`Updated "${name}"`, 'success');
        } else {
            await apiFetch('/workflows', { method: 'POST', body: JSON.stringify(body) });
            showToast(`Created "${name}"`, 'success');
        }
        initialEditorState = null;
        switchSection('workflows');
        loadWorkflows();
    } catch (e) { showToast(`Failed to save: ${e.message}`, 'error'); }
    finally {
        saveBtn.classList.remove('btn-loading');
        saveBtn.innerHTML = '<span class="btn-label">Save Workflow</span>';
        saveBtn.disabled = false;
    }
}

// ---- Logs ----
function initLogFilters() {
    document.getElementById('log-filter-pills').addEventListener('click', (e) => {
        const pill = e.target.closest('.log-filter-pill'); if (!pill) return;
        document.querySelectorAll('.log-filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active'); logStatusFilter = pill.dataset.status; logDisplayCount = 50; renderLogs();
    });
    const logSearch = document.getElementById('log-search');
    const debouncedLogRender = debounce(() => renderLogs(), 250);
    logSearch.addEventListener('input', () => { logSearchQuery = logSearch.value.trim().toLowerCase(); debouncedLogRender(); });
    const dateSelect = document.getElementById('log-date-select');
    setupCustomSelect(dateSelect);
    dateSelect.addEventListener('change', (e) => { logDateFilter = e.detail.value; renderLogs(); });
    document.getElementById('btn-load-more')?.addEventListener('click', () => { logDisplayCount += 50; renderLogs(); });
}

function getFilteredLogs() {
    let filtered = [...logs];
    if (logStatusFilter !== 'all') filtered = filtered.filter(l => l.status === logStatusFilter || (logStatusFilter === 'failed' && l.status === 'error'));
    if (logSearchQuery) filtered = filtered.filter(l => (l.workflow_name || '').toLowerCase().includes(logSearchQuery));
    if (logDateFilter !== 'all') {
        const now = new Date();
        const cutoff = logDateFilter === 'today' ? new Date(now.getFullYear(), now.getMonth(), now.getDate())
            : logDateFilter === '7days' ? new Date(now - 7 * 86400000)
            : new Date(now - 30 * 86400000);
        filtered = filtered.filter(l => l.started_at && new Date(l.started_at) >= cutoff);
    }
    return filtered;
}

async function loadLogs() {
    try { const data = await apiFetch('/logs'); logs = data.logs || []; renderLogs(); updateStats(); }
    catch (e) { console.error('Failed to load logs:', e); }
}

function renderLogs() {
    const list = document.getElementById('logs-list');
    const empty = document.getElementById('logs-empty');
    const filtered = getFilteredLogs();
    // Update count badges
    document.getElementById('log-count-all').textContent = logs.length;
    document.getElementById('log-count-success').textContent = logs.filter(l => l.status === 'success').length;
    document.getElementById('log-count-failed').textContent = logs.filter(l => l.status === 'failed' || l.status === 'error').length;
    document.getElementById('log-count-running').textContent = logs.filter(l => l.status === 'running').length;

    if (logs.length === 0) { list.style.display = 'none'; empty.style.display = 'flex'; document.getElementById('load-more-wrapper').style.display = 'none'; return; }
    list.style.display = 'flex'; empty.style.display = 'none';
    const toShow = filtered.slice(0, logDisplayCount);
    document.getElementById('load-more-wrapper').style.display = filtered.length > logDisplayCount ? 'flex' : 'none';

    list.innerHTML = toShow.map(log => {
        const statusCls = log.status === 'success' ? 'success' : log.status === 'running' ? 'running' : 'failed';
        const statusIcon = log.status === 'success' ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"/></svg>'
            : log.status === 'running' ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
        const steps = log.step_results || [];
        const stepsHtml = steps.map(s => {
            const icon = s.success ? '✓' : '✗'; const cls = s.success ? 'step-ok' : 'step-fail';
            const dur = s.duration_ms ? `${Math.round(s.duration_ms)}ms` : '';
            return `<div class="log-step ${cls}"><span class="log-step-status">${icon}</span><span class="log-step-name">${esc(s.step_name || s.action || 'Unknown')}</span><span class="log-step-dur">${dur}</span></div>`;
        }).join('');
        const time = log.started_at ? formatTime(log.started_at) : 'Unknown';
        const duration = log.total_duration_ms ? (log.total_duration_ms < 1000 ? `${log.total_duration_ms}ms` : `${(log.total_duration_ms / 1000).toFixed(1)}s`) : '—';
        const rerunBtn = log.workflow_id ? `<button class="btn btn-ghost btn-sm rerun-btn" onclick="event.stopPropagation();runWorkflow(${log.workflow_id},'${esc(log.workflow_name)}')">Re-run</button>` : '';
        return `<div class="log-card" onclick="this.classList.toggle('expanded')" role="button" tabindex="0">
            <div class="log-status-icon ${statusCls}">${statusIcon}</div>
            <div class="log-info"><div class="log-name">${esc(log.workflow_name)}</div><div class="log-time">${time}</div></div>
            <div class="log-duration">${duration}</div>
            <svg class="log-expand-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6,9 12,15 18,9"/></svg>
            ${steps.length > 0 ? `<div class="log-detail">${stepsHtml}${rerunBtn}</div>` : ''}
        </div>`;
    }).join('');
}

// Log card Enter/Space
document.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('log-card')) { e.preventDefault(); e.target.classList.toggle('expanded'); }
});

document.getElementById('btn-refresh-logs')?.addEventListener('click', () => { loadLogs(); resetLogRefreshCountdown(); });
document.getElementById('btn-clear-logs')?.addEventListener('click', () => {
    showConfirmModal('Clear All Logs', 'This will permanently delete all execution logs.', 'Clear All', async () => {
        closeConfirmModal();
        try { await apiFetch('/logs', { method: 'DELETE' }); showToast('Logs cleared', 'info'); loadLogs(); }
        catch (e) { showToast('Failed to clear logs', 'error'); }
    });
});

// Auto-refresh countdown
function startLogRefreshLoop() {
    logRefreshCountdown = 15;
    logRefreshInterval = setInterval(() => { if (currentSection === 'logs') loadLogs(); resetLogRefreshCountdown(); }, 15000);
    logCountdownInterval = setInterval(() => {
        if (currentSection === 'logs') {
            logRefreshCountdown = Math.max(0, logRefreshCountdown - 1);
            document.getElementById('auto-refresh-text').textContent = `Auto-refresh in ${logRefreshCountdown}s`;
            const fill = document.getElementById('auto-refresh-fill');
            if (fill) fill.style.width = `${((15 - logRefreshCountdown) / 15) * 100}%`;
        }
    }, 1000);
}
function resetLogRefreshCountdown() { logRefreshCountdown = 15; }

// ---- Health ----
function startHealthCheckLoop() { setInterval(checkServerHealth, healthCheckInterval); }
async function checkServerHealth() {
    try {
        await apiFetch('/health');
        document.querySelector('.status-dot').classList.remove('disconnected');
        document.querySelector('.status-text').textContent = 'Connected';
        if (!isServerConnected) { isServerConnected = true; healthCheckInterval = 30000; }
    } catch {
        document.querySelector('.status-dot').classList.add('disconnected');
        document.querySelector('.status-text').textContent = 'Disconnected';
        if (isServerConnected) { isServerConnected = false; healthCheckInterval = 60000; }
    }
}

// ---- Settings ----
function initSettings() {
    const autoToggle = document.getElementById('autostart-toggle');
    autoToggle.addEventListener('change', async () => {
        const action = autoToggle.checked ? 'install' : 'uninstall';
        try { await apiFetch(`/settings/autostart/${action}`, { method: 'POST' }); showToast(`Autostart ${autoToggle.checked ? 'enabled' : 'disabled'}`, 'success'); document.getElementById('autostart-label').textContent = autoToggle.checked ? 'Enabled' : 'Disabled'; }
        catch (e) { autoToggle.checked = !autoToggle.checked; showToast(`Failed: ${e.message}`, 'error'); }
    });
    document.getElementById('notif-toggle').addEventListener('change', function() { document.getElementById('notif-label').textContent = this.checked ? 'Enabled' : 'Disabled'; showToast(`Desktop notifications ${this.checked ? 'enabled' : 'disabled'}`, 'info'); });
    document.getElementById('btn-connect-gcal').addEventListener('click', () => showToast('Configure Google Calendar in server settings (see README)', 'info'));
    document.getElementById('btn-export-workflows').addEventListener('click', () => {
        const blob = new Blob([JSON.stringify(workflows, null, 2)], { type: 'application/json' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'autoflow-workflows.json'; a.click(); showToast('Workflows exported', 'success');
    });
    document.getElementById('btn-import-workflows').addEventListener('click', () => document.getElementById('import-file-input').click());
    document.getElementById('import-file-input').addEventListener('change', async (e) => {
        const file = e.target.files[0]; if (!file) return;
        try { const text = await file.text(); JSON.parse(text); showToast('Import functionality coming soon', 'info'); }
        catch { showToast('Invalid JSON file', 'error'); }
        e.target.value = '';
    });
    document.getElementById('btn-delete-all-workflows').addEventListener('click', () => {
        showConfirmModal('Delete All Workflows', 'This will permanently delete ALL workflows. This cannot be undone.', 'Delete All', async () => {
            closeConfirmModal();
            try { for (const wf of workflows) { await apiFetch(`/workflows/${wf.id}`, { method: 'DELETE' }); } showToast('All workflows deleted', 'info'); loadWorkflows(); }
            catch (e) { showToast(`Failed: ${e.message}`, 'error'); }
        });
    });
}

// ---- AI Settings ----
async function initAISettings() {
    const providerSelect = document.getElementById('ai-provider');
    const apiKeyGroup = document.getElementById('ai-apikey-group');
    const apiKeyInput = document.getElementById('ai-apikey');
    const modelInput = document.getElementById('ai-model');

    providerSelect.addEventListener('change', (e) => {
        const val = e.detail ? e.detail.value : providerSelect.dataset.value;
        apiKeyGroup.style.display = val === 'openai' ? 'block' : 'none';
        
        // Auto-update model placeholder based on provider if empty
        if (!modelInput.value) {
            modelInput.placeholder = val === 'ollama' ? 'qwen2.5:1.5b' : 'gpt-4o-mini';
        }
    });

    try {
        const settings = await apiFetch('/ai/settings');
        const defaultProvider = settings.provider || 'ollama';
        
        // Update Custom Select visually
        providerSelect.dataset.value = defaultProvider;
        const opt = providerSelect.querySelector(`.custom-select-option[data-value="${defaultProvider}"]`);
        if (opt) {
            const labelEl = opt.querySelector('span:not(.action-option-icon)') || opt.querySelector('span');
            providerSelect.querySelector('.custom-select-value').textContent = labelEl ? labelEl.textContent : opt.textContent.trim();
            providerSelect.querySelectorAll('.custom-select-option').forEach(o => o.classList.remove('selected'));
            opt.classList.add('selected');
        }

        apiKeyInput.value = settings.api_key || '';
        modelInput.value = settings.model || (defaultProvider === 'ollama' ? 'qwen2.5:1.5b' : 'gpt-4o-mini');
        
        providerSelect.dispatchEvent(new CustomEvent('change', { detail: { value: defaultProvider } }));
    } catch (e) {
        console.error('Failed to load AI settings', e);
    }

    document.getElementById('btn-save-ai-settings').addEventListener('click', async (e) => {
        const btn = e.target;
        const providerVal = providerSelect.dataset.value;
        const modelName = modelInput.value || (providerVal === 'ollama' ? 'qwen2.5:1.5b' : 'gpt-4o-mini');
        
        const saveSettings = async () => {
            btn.classList.add('btn-loading');
            btn.disabled = true;
            try {
                await apiFetch('/ai/settings', {
                    method: 'POST',
                    body: JSON.stringify({
                        provider: providerVal,
                        api_key: apiKeyInput.value,
                        model: modelName
                    })
                });
                showToast('AI Settings saved successfully', 'success');
            } catch (err) {
                showToast(`Failed to save AI Settings: ${err.message}`, 'error');
            } finally {
                btn.classList.remove('btn-loading');
                btn.disabled = false;
            }
        };

        if (providerVal === 'ollama') {
            const BIG_MODELS = ['llama3:8b', 'mistral:7b', 'qwen2.5:7b', 'llama3.1:8b', 'gemma:7b', 'llama3.2:3b'];
            
            const performOllamaCheck = async () => {
                btn.classList.add('btn-loading');
                btn.disabled = true;
                try {
                    const checkState = await apiFetch(`/ai/ollama/check?model=${encodeURIComponent(modelName)}`);
                    if (!checkState.installed) {
                        btn.classList.remove('btn-loading');
                        btn.disabled = false;
                        showConfirmModal('Model Not Installed', `The model "${modelName}" is not currently installed on your local machine. Do you want AutoFlow to download it now? (This will take a few minutes)`, 'Yes, Install', async () => {
                            closeConfirmModal();
                            btn.classList.add('btn-loading');
                            btn.disabled = true;
                            showToast(`Installing ${modelName}... Please wait.`, 'info');
                            try {
                                await apiFetch('/ai/ollama/pull', { method: 'POST', body: JSON.stringify({ model_name: modelName }) });
                                showToast(`${modelName} installed successfully!`, 'success');
                                await saveSettings();
                            } catch (e) {
                                showToast(`Failed to install model: ${e.message}`, 'error');
                                btn.classList.remove('btn-loading');
                                btn.disabled = false;
                            }
                        });
                    } else {
                        btn.classList.remove('btn-loading');
                        btn.disabled = false;
                        await saveSettings();
                    }
                } catch (e) {
                    showToast(`Failed to verify local model: ${e.message}`, 'error');
                    btn.classList.remove('btn-loading');
                    btn.disabled = false;
                }
            };

            const isBig = BIG_MODELS.some(m => modelName.toLowerCase().startsWith(m.split(':')[0]));
            if (isBig) {
                showConfirmModal('Large Model Warning', `The model "${modelName}" is quite large and requires significant RAM (8GB-16GB+) to run smoothly locally. Are you sure you want to proceed?`, 'Proceed', () => {
                    closeConfirmModal();
                    performOllamaCheck();
                });
            } else {
                performOllamaCheck();
            }
        } else {
            // OpenAI saves instantly
            saveSettings();
        }
    });
}

// ---- AI Editor ----
function initAIEditor() {
    // Tab switching
    document.getElementById('editor-tabs').addEventListener('click', (e) => {
        const pill = e.target.closest('.filter-pill');
        if (!pill) return;
        document.querySelectorAll('#editor-tabs .filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        
        const tab = pill.dataset.tab;
        document.getElementById('editor-manual-pane').style.display = tab === 'manual' ? 'block' : 'none';
        document.getElementById('editor-ai-pane').style.display = tab === 'ai' ? 'block' : 'none';
    });

    // Voice recognition
    const btnMic = document.getElementById('btn-ai-mic');
    const promptInput = document.getElementById('ai-prompt-input');
    const micStatus = document.getElementById('ai-mic-status');
    let recognition = null;

    if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = () => {
            btnMic.style.display = 'none';
            micStatus.style.display = 'flex';
        };
        recognition.onresult = (e) => {
            const transcript = e.results[0][0].transcript;
            promptInput.value = (promptInput.value + ' ' + transcript).trim();
        };
        recognition.onerror = (e) => {
            showToast(`Microphone error: ${e.error}`, 'error');
            resetMicUI();
        };
        recognition.onend = () => {
            resetMicUI();
        };
    } else {
        btnMic.style.display = 'none';
    }

    btnMic.addEventListener('click', () => {
        if (recognition) recognition.start();
    });

    function resetMicUI() {
        btnMic.style.display = 'flex';
        micStatus.style.display = 'none';
    }

    // AI Generation
    document.getElementById('btn-ai-generate').addEventListener('click', async (e) => {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            showToast('Please describe the workflow you want to generate', 'error');
            return;
        }

        const btn = e.target;
        const originalHtml = btn.innerHTML;
        btn.classList.add('btn-loading');
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-spinner" style="margin-right: 8px;"></span> Generating...';

        try {
            const wf = await apiFetch('/ai/generate', {
                method: 'POST',
                body: JSON.stringify({ prompt })
            });

            // Populate Manual UI
            document.getElementById('wf-name').value = wf.name || '';
            document.getElementById('wf-description').value = wf.description || '';
            
            const trigger = wf.trigger || {};
            const type = trigger.type || 'manual';
            const typeLabels = { manual: 'Manual', login: 'On Login', cron: 'Cron Schedule', interval: 'Interval' };
            setCustomSelectValue('wf-trigger-select', type, typeLabels[type] || type);
            
            const tcg = document.getElementById('trigger-config-group');
            if (type === 'cron') {
                tcg.classList.add('open');
                document.getElementById('trigger-config-label').innerHTML = 'Cron Expression <span class="required-asterisk">*</span>';
                document.getElementById('wf-trigger-config').value = trigger.schedule || '';
            } else if (type === 'interval') {
                tcg.classList.add('open');
                document.getElementById('trigger-config-label').innerHTML = 'Interval (minutes) <span class="required-asterisk">*</span>';
                document.getElementById('wf-trigger-config').value = trigger.interval_minutes || '';
            } else {
                tcg.classList.remove('open');
            }

            // Populate steps
            editorSteps = (wf.steps || []).map(s => {
                const step = { action: s.type, params: {} };
                if (s.args) {
                    // Normalize known LLM key variants to match ACTION_PARAMS
                    const keyMap = {
                        'app_name': 'command',
                        'application': 'command',
                        'app': 'command',
                        'shell_command': 'command',
                        'cmd': 'command',
                        'link': 'url',
                        'seconds': 'timeout',
                        'directory': 'cwd',
                        'working_directory': 'cwd',
                        'dir': 'cwd',
                    };
                    for (const [k, v] of Object.entries(s.args)) {
                        const normalizedKey = keyMap[k] || k;
                        if (normalizedKey === 'timeout' || normalizedKey === 'lookahead_hours' || normalizedKey === 'interval_minutes') {
                            step.params[normalizedKey] = parseInt(v) || 60;
                        } else if (normalizedKey === 'args') {
                            step.params[normalizedKey] = Array.isArray(v) ? v : (typeof v === 'string' && v ? v.split(',').map(s => s.trim()).filter(Boolean) : []);
                        } else {
                            step.params[normalizedKey] = Array.isArray(v) ? v : String(v);
                        }
                    }
                }
                return step;
            });
            
            renderSteps();
            clearValidation();
            
            // Switch back to manual tab
            document.querySelector('#editor-tabs .filter-pill[data-tab="manual"]').click();
            promptInput.value = ''; // clear prompt
            
            // Show Verify Modal
            openModal('ai-verify-modal');
        } catch (err) {
            showToast(`Generation failed: ${err.message}`, 'error');
        } finally {
            btn.classList.remove('btn-loading');
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    });

    document.getElementById('ai-verify-ok').addEventListener('click', () => {
        closeModal('ai-verify-modal');
    });
}

// ---- Templates ----
function initTemplates() {
    const grid = document.getElementById('templates-grid');
    grid.innerHTML = WORKFLOW_TEMPLATES.map((t, i) => `<div class="template-card" data-template="${i}"><div class="template-icon">${t.icon}</div><h4>${t.name}</h4><p>${t.description}</p></div>`).join('');
    grid.addEventListener('click', (e) => {
        const card = e.target.closest('.template-card'); if (!card) return;
        const t = WORKFLOW_TEMPLATES[parseInt(card.dataset.template)];
        closeModal('templates-modal');
        editingWorkflowId = null; editorSteps = t.steps.map(s => ({ ...s }));
        document.getElementById('editor-title').textContent = 'New Workflow';
        document.getElementById('wf-name').value = t.name;
        document.getElementById('wf-description').value = t.description;
        setCustomSelectValue('wf-trigger-select', 'manual', 'Manual');
        document.getElementById('trigger-config-group').classList.remove('open');
        clearValidation(); renderSteps(); switchSection('editor');
        initialEditorState = getEditorSnapshot();
    });
    document.getElementById('btn-start-template')?.addEventListener('click', () => openModal('templates-modal'));
    document.getElementById('templates-modal-close')?.addEventListener('click', () => closeModal('templates-modal'));
}

function openModal(id) { const m = document.getElementById(id); if (m) { m.style.display = 'flex'; trapFocus(m); } }
function closeModal(id) { const m = document.getElementById(id); if (m) { m.style.display = 'none'; if (m._trapHandler) m.removeEventListener('keydown', m._trapHandler); } }

// ---- Confirm Modal Init ----
function initConfirmModal() {
    document.getElementById('confirm-modal-cancel').addEventListener('click', closeConfirmModal);
    document.getElementById('confirm-modal-confirm').addEventListener('click', () => { if (confirmCallback) confirmCallback(); });
    document.getElementById('confirm-modal').addEventListener('click', (e) => { if (e.target === e.currentTarget) closeConfirmModal(); });
}

// ---- Keyboard Shortcuts ----
function initKeyboardShortcuts() {
    document.getElementById('btn-shortcuts-help').addEventListener('click', () => openModal('shortcuts-modal'));
    document.getElementById('shortcuts-modal-close').addEventListener('click', () => closeModal('shortcuts-modal'));
    document.getElementById('shortcuts-modal').addEventListener('click', (e) => { if (e.target === e.currentTarget) closeModal('shortcuts-modal'); });

    document.addEventListener('keydown', (e) => {
        const tag = document.activeElement?.tagName;
        const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

        // Escape always works
        if (e.key === 'Escape') {
            const cm = document.getElementById('confirm-modal'); if (cm.style.display !== 'none') { closeConfirmModal(); return; }
            const sm = document.getElementById('shortcuts-modal'); if (sm.style.display !== 'none') { closeModal('shortcuts-modal'); return; }
            const tm = document.getElementById('templates-modal'); if (tm.style.display !== 'none') { closeModal('templates-modal'); return; }
            document.querySelectorAll('.custom-select.open').forEach(s => { s.classList.remove('open'); const dd = s.querySelector('.custom-select-dropdown'); if (dd) { dd.style.removeProperty('bottom'); dd.style.removeProperty('top'); dd.classList.remove('flip-up'); } });
            return;
        }

        if (isInput) return;

        switch (e.key) {
            case 'n': case 'N': e.preventDefault(); showCreateModal(); break;
            case '1': e.preventDefault(); switchSection('workflows'); break;
            case '2': e.preventDefault(); switchSection('logs'); break;
            case '3': e.preventDefault(); switchSection('settings'); break;
            case '?': e.preventDefault(); openModal('shortcuts-modal'); break;
            case '/':
                e.preventDefault();
                if (currentSection === 'workflows') document.getElementById('workflow-search')?.focus();
                else if (currentSection === 'logs') document.getElementById('log-search')?.focus();
                break;
        }
    });
}
