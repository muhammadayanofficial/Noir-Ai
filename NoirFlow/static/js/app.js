(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const toastRegion = $('#toastRegion');

  function toast(message, kind = '') {
    if (!toastRegion) return;
    const node = document.createElement('div');
    node.className = `toast ${kind}`.trim();
    node.textContent = message;
    toastRegion.appendChild(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  const titleMap = {
    overview: 'Overview', projects: 'Projects', tasks: 'Tasks',
    calendar: 'Calendar', focus: 'Focus room', notes: 'Notebook', clients: 'Clients'
  };

  function setView(view, updateUrl = true) {
    if (!titleMap[view]) view = 'overview';
    $$('[data-view]').forEach(panel => {
      panel.classList.toggle('view-active', panel.dataset.view === view);
    });
    $$('[data-nav]').forEach(button => {
      button.classList.toggle('active', button.dataset.nav === view && button.classList.contains('rail-link'));
    });
    const crumb = $('#crumbCurrent');
    if (crumb) crumb.textContent = titleMap[view];
    if (updateUrl) {
      const next = view === 'overview' ? window.location.pathname : `${window.location.pathname}?view=${encodeURIComponent(view)}`;
      window.history.replaceState({ view }, '', next);
    }
    document.body.dataset.initialView = view;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  $$('[data-nav]').forEach(button => button.addEventListener('click', () => setView(button.dataset.nav)));
  window.addEventListener('popstate', () => {
    const view = new URLSearchParams(window.location.search).get('view') || 'overview';
    setView(view, false);
  });
  setView(document.body.dataset.initialView || 'overview', false);

  // Modal controls keep forms in one consistent place without leaving the current view.
  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    const firstInput = $('input:not([type="hidden"]), select, textarea', modal);
    if (firstInput) window.setTimeout(() => firstInput.focus(), 40);
  }
  function closeModal(modal) {
    if (!modal) return;
    modal.hidden = true;
    if (!$$('.modal-backdrop:not([hidden])').length) document.body.style.overflow = '';
  }
  $$('[data-open-modal]').forEach(button => button.addEventListener('click', () => openModal(button.dataset.openModal)));
  $$('[data-close-modal]').forEach(button => button.addEventListener('click', () => closeModal(button.closest('.modal-backdrop'))));
  $$('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('mousedown', event => {
      if (event.target === backdrop) closeModal(backdrop);
    });
  });
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      const open = $('.modal-backdrop:not([hidden])');
      if (open) closeModal(open);
    }
  });

  // Use server-backed status updates for both the list view and the drag-and-drop board.
  async function saveTaskStatus(taskId, status, reloadAfter = true) {
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Could not update task status.');
      if (reloadAfter) window.location.reload();
      return true;
    } catch (error) {
      toast(error.message || 'Could not update task status.', 'error');
      return false;
    }
  }

  $$('[data-status-task]').forEach(select => {
    select.addEventListener('change', async () => {
      select.disabled = true;
      await saveTaskStatus(select.dataset.statusTask, select.value);
      select.disabled = false;
    });
  });

  let draggedTaskId = null;
  $$('.task-card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', event => {
      draggedTaskId = card.dataset.taskId;
      card.classList.add('dragging');
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', draggedTaskId);
      }
    });
    card.addEventListener('dragend', () => {
      draggedTaskId = null;
      card.classList.remove('dragging');
      $$('.kanban-column').forEach(column => column.classList.remove('drag-over'));
    });
  });
  $$('.kanban-column').forEach(column => {
    column.addEventListener('dragover', event => {
      event.preventDefault();
      column.classList.add('drag-over');
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    });
    column.addEventListener('dragleave', event => {
      if (!column.contains(event.relatedTarget)) column.classList.remove('drag-over');
    });
    column.addEventListener('drop', async event => {
      event.preventDefault();
      column.classList.remove('drag-over');
      const taskId = (event.dataTransfer && event.dataTransfer.getData('text/plain')) || draggedTaskId;
      if (taskId && column.dataset.dropStatus) await saveTaskStatus(taskId, column.dataset.dropStatus);
    });
  });

  $$('[data-delete-task]').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm('Delete this task?')) return;
    try {
      const response = await fetch(`/tasks/${encodeURIComponent(button.dataset.deleteTask)}/delete`, { method: 'POST' });
      if (!response.ok) throw new Error('Could not delete the task.');
      window.location.reload();
    } catch (error) {
      toast(error.message || 'Could not delete the task.', 'error');
    }
  }));

  // Instant task list filtering.
  const taskSearch = $('#taskSearch');
  const priorityFilter = $('#priorityFilter');
  function filterTaskRows() {
    const query = (taskSearch?.value || '').trim().toLowerCase();
    const priority = priorityFilter?.value || '';
    $$('[data-task-row]').forEach(row => {
      const matchesQuery = !query || (row.dataset.search || '').includes(query);
      const matchesPriority = !priority || row.dataset.priority === priority;
      row.hidden = !(matchesQuery && matchesPriority);
    });
  }
  taskSearch?.addEventListener('input', filterTaskRows);
  priorityFilter?.addEventListener('change', filterTaskRows);

  // One timer state powers both timer presentations so the two views remain synchronized.
  let selectedMinutes = 25;
  let remainingSeconds = selectedMinutes * 60;
  let intervalId = null;
  let isRunning = false;
  let sessionLogged = false;

  const displayIds = ['timerDisplay', 'timerDisplayLarge'];
  const statusIds = ['timerStatus', 'timerStatusLarge'];
  const startIds = ['timerStart', 'timerStartLarge'];
  const ringIds = ['timerRing', 'timerRingLarge'];

  function formatSeconds(total) {
    const safe = Math.max(0, total);
    return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
  }
  function setTimerStatus(value) {
    statusIds.forEach(id => { const node = document.getElementById(id); if (node) node.textContent = value; });
  }
  function setTimerStartText(value) {
    startIds.forEach(id => {
      const node = document.getElementById(id);
      if (node) node.innerHTML = `${value} <span>↗</span>`;
    });
  }
  function renderTimer() {
    displayIds.forEach(id => { const node = document.getElementById(id); if (node) node.textContent = formatSeconds(remainingSeconds); });
    const progress = (1 - remainingSeconds / Math.max(1, selectedMinutes * 60)) * 360;
    ringIds.forEach(id => { const node = document.getElementById(id); if (node) node.style.setProperty('--timer-progress', `${progress}deg`); });
  }
  function stopInterval() {
    if (intervalId !== null) window.clearInterval(intervalId);
    intervalId = null;
    isRunning = false;
  }
  function getCurrentProject() {
    const large = $('#focusProjectLarge')?.value || '';
    const small = $('#focusProject')?.value || '';
    return large || small || '';
  }
  function getCurrentNote() {
    const text = ($('#focusNote')?.value || '').trim();
    return text || 'Deep work';
  }
  async function logCompletedSession() {
    if (sessionLogged) return;
    sessionLogged = true;
    try {
      const response = await fetch('/api/focus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_minutes: selectedMinutes, project_id: getCurrentProject(), note: getCurrentNote() })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Session could not be logged.');
      toast(`Focus session saved · ${selectedMinutes} minutes`);
    } catch (error) {
      toast(error.message || 'Session completed, but it could not be saved.', 'error');
    }
  }
  function pauseTimer() {
    stopInterval();
    setTimerStatus('SESSION PAUSED');
    setTimerStartText('Resume session');
  }
  function startTimer() {
    if (isRunning) {
      pauseTimer();
      return;
    }
    if (remainingSeconds <= 0) {
      remainingSeconds = selectedMinutes * 60;
      sessionLogged = false;
    }
    isRunning = true;
    setTimerStatus('IN THE FLOW');
    setTimerStartText('Pause session');
    intervalId = window.setInterval(() => {
      remainingSeconds -= 1;
      renderTimer();
      if (remainingSeconds <= 0) {
        stopInterval();
        remainingSeconds = 0;
        renderTimer();
        setTimerStatus('SESSION COMPLETE');
        setTimerStartText('Start another');
        logCompletedSession();
      }
    }, 1000);
  }
  function resetTimer() {
    stopInterval();
    remainingSeconds = selectedMinutes * 60;
    sessionLogged = false;
    setTimerStatus('READY WHEN YOU ARE');
    setTimerStartText('Begin session');
    renderTimer();
  }
  function setTimerMinutes(minutes) {
    stopInterval();
    selectedMinutes = minutes;
    remainingSeconds = minutes * 60;
    sessionLogged = false;
    $$('.timer-preset').forEach(button => button.classList.toggle('active', Number(button.dataset.minutes) === minutes));
    setTimerStatus('READY WHEN YOU ARE');
    setTimerStartText('Begin session');
    renderTimer();
  }
  startIds.forEach(id => document.getElementById(id)?.addEventListener('click', startTimer));
  ['timerReset', 'timerResetLarge'].forEach(id => document.getElementById(id)?.addEventListener('click', resetTimer));
  $$('.timer-preset').forEach(button => button.addEventListener('click', () => setTimerMinutes(Number(button.dataset.minutes))));
  renderTimer();

  // Build a compact monthly calendar and mark dates from the server-rendered deadline list.
  const calendarGrid = $('#calendarGrid');
  const calendarMonth = $('#calendarMonth');
  const deadlineMap = new Map();
  $$('.deadline-item[data-date]').forEach(item => {
    const date = item.dataset.date;
    if (!deadlineMap.has(date)) deadlineMap.set(date, new Set());
    deadlineMap.get(date).add(item.dataset.kind);
  });
  let visibleMonth = new Date();
  visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
  function renderCalendar() {
    if (!calendarGrid || !calendarMonth) return;
    calendarGrid.innerHTML = '';
    calendarMonth.textContent = visibleMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    ['Su','Mo','Tu','We','Th','Fr','Sa'].forEach(day => {
      const node = document.createElement('span');
      node.className = 'cal-weekday'; node.textContent = day; calendarGrid.appendChild(node);
    });
    const firstDay = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
    const start = new Date(firstDay);
    start.setDate(firstDay.getDate() - firstDay.getDay());
    const today = new Date();
    const todayString = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    for (let index = 0; index < 42; index += 1) {
      const d = new Date(start);
      d.setDate(start.getDate() + index);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      const kinds = deadlineMap.get(key) || new Set();
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cal-day';
      if (d.getMonth() !== visibleMonth.getMonth()) button.classList.add('outside');
      if (key === todayString) button.classList.add('today');
      if (kinds.has('task')) button.classList.add('has-task');
      if (kinds.has('project')) button.classList.add('has-project');
      button.textContent = String(d.getDate());
      button.title = kinds.size ? `${key}: ${Array.from(kinds).join(' and ')} deadline` : key;
      button.addEventListener('click', () => {
        const matches = $$('.deadline-item[data-date]').filter(item => item.dataset.date === key);
        if (matches.length) {
          matches[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
          matches[0].classList.add('date-highlight');
          window.setTimeout(() => matches[0].classList.remove('date-highlight'), 1400);
        } else {
          toast(`No deadline listed for ${key}.`);
        }
      });
      calendarGrid.appendChild(button);
    }
  }
  $('#monthPrev')?.addEventListener('click', () => { visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1); renderCalendar(); });
  $('#monthNext')?.addEventListener('click', () => { visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1); renderCalendar(); });
  renderCalendar();

  // Selecting a project's Plan with AI action fills the planner without fabricating an AI result.
  $$('[data-plan-project]').forEach(button => button.addEventListener('click', () => {
    setView('projects');
    const select = $('#plannerProject');
    if (select) select.value = button.dataset.planProject;
    $('#plannerGoal')?.focus();
    $('#ai-planner-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }));
  $('#generatePlan')?.addEventListener('click', async () => {
    const button = $('#generatePlan');
    const output = $('#aiResult');
    if (!output || !button) return;
    output.hidden = false;
    output.classList.remove('error');
    output.textContent = 'Thinking through the milestones…';
    button.disabled = true;
    button.textContent = 'Building plan…';
    try {
      const response = await fetch('/api/ai/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: $('#plannerProject')?.value || '', goal: $('#plannerGoal')?.value || '' })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'The plan could not be generated.');
      output.textContent = data.text;
    } catch (error) {
      output.classList.add('error');
      output.textContent = error.message || 'The AI planner is not available right now.';
    } finally {
      button.disabled = false;
      button.innerHTML = 'Build a plan <span>↗</span>';
    }
  });

  // Keep client-side filtering, timers and board interactions accessible from keyboard as well.
  $$('.saved, [role="button"][data-query]').forEach(node => {
    node.addEventListener('keydown', event => {
      if ((event.key === 'Enter' || event.key === ' ') && node.dataset.query) {
        event.preventDefault();
        node.click();
      }
    });
  });
})();
