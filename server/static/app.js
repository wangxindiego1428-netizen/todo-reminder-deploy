const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
const REPEAT_CN = { none: '', daily: '每日', weekly: '每周', monthly: '每月', yearly: '每年' };

const pad = n => String(n).padStart(2, '0');
const fmt = dt => `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
const todayStr = () => fmt(new Date());
function shiftDate(str, days) {
  const [y, m, d] = str.split('-').map(Number);
  return fmt(new Date(y, m - 1, d + days));
}

const params = new URLSearchParams(location.search);
let viewDate = params.get('date') || todayStr();

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = '/login'; return null; }
  return r.json();
}
function jsonOpts(method, body) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function titleFor(date) {
  const t = todayStr();
  if (date === t) return '今日待办';
  if (date === shiftDate(t, 1)) return '明日待办';
  if (date === shiftDate(t, -1)) return '昨日待办';
  const [, m, d] = date.split('-').map(Number);
  return `${m}月${d}日待办`;
}
function dateLabel(date) {
  const [y, m, d] = date.split('-').map(Number);
  return `${m}月${d}日 ${WEEK[new Date(y, m - 1, d).getDay()]}`;
}

function renderHeader(open) {
  document.getElementById('heading').textContent = titleFor(viewDate);
  document.getElementById('dateBtn').textContent = dateLabel(viewDate);
  document.getElementById('count').textContent = `· ${open} 项未完成`;
  document.getElementById('todayBtn').hidden = (viewDate === todayStr());
}

async function load() {
  const data = await api(`/api/todos?date=${viewDate}`);
  if (!data) return;
  const list = document.getElementById('list');
  list.innerHTML = '';
  renderHeader(data.todos.filter(t => !t.done).length);
  document.getElementById('empty').hidden = data.todos.length > 0;
  data.todos.forEach((t, i) => {
    const li = renderItem(t);
    li.style.animationDelay = `${Math.min(i, 8) * 40}ms`;
    list.appendChild(li);
  });
}

function setDate(date) { viewDate = date; load(); }

function renderItem(t) {
  const li = document.createElement('li');
  li.className = t.done ? 'item done' : 'item';

  const time = document.createElement('span');
  time.className = 'time';
  time.textContent = t.remind_at || '';

  const title = document.createElement('span');
  title.className = 'title';
  title.textContent = t.title;
  if (t.repeat && t.repeat !== 'none') {
    const r = document.createElement('span');
    r.className = 'rep';
    r.textContent = ` 🔁${REPEAT_CN[t.repeat] || ''}`;
    title.appendChild(r);
  }
  if (t.rolled_from) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = ' · 往日遗留';
    title.appendChild(tag);
  }
  title.title = '点击编辑';
  title.onclick = () => enterEdit(t, li);

  const del = document.createElement('button');
  del.type = 'button'; del.className = 'del'; del.textContent = '✕';
  del.setAttribute('aria-label', '删除');
  del.onclick = async () => { await api(`/api/todos/${t.id}`, { method: 'DELETE' }); load(); };

  const toggle = document.createElement('span');
  toggle.className = 'toggle';
  toggle.setAttribute('role', 'checkbox');
  toggle.setAttribute('aria-checked', t.done ? 'true' : 'false');
  toggle.setAttribute('aria-label', t.title);
  toggle.setAttribute('tabindex', '0');
  const doToggle = async () => {
    await api(`/api/todos/${t.id}/done`, jsonOpts('POST', { done: !t.done, date: viewDate }));
    load();
  };
  toggle.onclick = doToggle;
  toggle.onkeydown = e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); doToggle(); } };

  li.append(time, title, del, toggle);
  return li;
}

function enterEdit(t, li) {
  li.className = 'item editing';
  li.innerHTML = '';

  const titleIn = document.createElement('input');
  titleIn.type = 'text'; titleIn.className = 'edit-title'; titleIn.value = t.title;

  const whenIn = document.createElement('input');
  whenIn.type = 'datetime-local'; whenIn.className = 'edit-when';
  whenIn.value = t.remind_at ? `${t.date}T${t.remind_at}` : '';

  const repSel = document.createElement('select');
  repSel.className = 'edit-rep';
  for (const [val, label] of Object.entries({ none: '不重复', daily: '每日', weekly: '每周', monthly: '每月', yearly: '每年' })) {
    const o = document.createElement('option');
    o.value = val; o.textContent = label;
    if (val === t.repeat) o.selected = true;
    repSel.appendChild(o);
  }

  const save = document.createElement('button');
  save.type = 'button'; save.className = 'edit-save'; save.textContent = '保存';
  save.onclick = async () => {
    const title = titleIn.value.trim();
    if (!title) return;
    let date = t.date, remind_at = null;
    if (whenIn.value) { const [d, tm] = whenIn.value.split('T'); date = d; remind_at = tm.slice(0, 5); }
    await api(`/api/todos/${t.id}`, jsonOpts('PATCH', { title, date, remind_at, repeat: repSel.value }));
    setDate(date);
  };

  const cancel = document.createElement('button');
  cancel.type = 'button'; cancel.className = 'edit-cancel'; cancel.textContent = '取消';
  cancel.onclick = () => load();

  titleIn.addEventListener('keydown', e => { if (e.key === 'Enter') save.click(); if (e.key === 'Escape') cancel.click(); });

  li.append(titleIn, whenIn, repSel, save, cancel);
  titleIn.focus();
}

async function add() {
  const ti = document.getElementById('title');
  const title = ti.value.trim();
  if (!title) return;
  const when = document.getElementById('when').value;
  const repeat = document.getElementById('repeat').value;
  let date = viewDate, remind_at = null;
  if (when) { const [d, t] = when.split('T'); date = d; remind_at = t.slice(0, 5); }
  await api('/api/todos', jsonOpts('POST', { title, date, remind_at, repeat }));
  ti.value = '';
  document.getElementById('when').value = '';
  document.getElementById('repeat').value = 'none';
  ti.focus();
  setDate(date);
}

document.getElementById('add').onclick = add;
document.getElementById('title').addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
document.getElementById('prev').onclick = () => setDate(shiftDate(viewDate, -1));
document.getElementById('next').onclick = () => setDate(shiftDate(viewDate, 1));
document.getElementById('todayBtn').onclick = () => setDate(todayStr());

const datePick = document.getElementById('datePick');
document.getElementById('dateBtn').onclick = () => {
  datePick.value = viewDate;
  if (datePick.showPicker) { try { datePick.showPicker(); } catch (e) { datePick.focus(); } }
  else { datePick.focus(); }
};
datePick.onchange = () => { if (datePick.value) setDate(datePick.value); };

load();
