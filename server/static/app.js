const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

function todayStr() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
const DATE = todayStr();

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = '/login'; return null; }
  return r.json();
}

function jsonOpts(method, body) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function updateSub(todos) {
  const d = new Date();
  const open = todos.filter(t => !t.done).length;
  document.getElementById('sub').textContent =
    `${d.getMonth() + 1}月${d.getDate()}日 ${WEEK[d.getDay()]} · ${open} 项未完成`;
}

async function load() {
  const data = await api(`/api/todos?date=${DATE}`);
  if (!data) return;
  const list = document.getElementById('list');
  list.innerHTML = '';
  document.getElementById('empty').hidden = data.todos.length > 0;
  updateSub(data.todos);
  data.todos.forEach((t, i) => {
    const li = renderItem(t);
    li.style.animationDelay = `${Math.min(i, 8) * 40}ms`;
    list.appendChild(li);
  });
}

function renderItem(t) {
  const li = document.createElement('li');
  li.className = t.done ? 'item done' : 'item';

  const time = document.createElement('span');
  time.className = 'time';
  time.textContent = t.remind_at || '';

  const title = document.createElement('span');
  title.className = 'title';
  title.textContent = t.title;
  if (t.rolled_from) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = ' · 往日遗留';
    title.appendChild(tag);
  }

  const del = document.createElement('button');
  del.type = 'button';
  del.className = 'del';
  del.textContent = '✕';
  del.setAttribute('aria-label', '删除');
  del.onclick = async () => { await api(`/api/todos/${t.id}`, { method: 'DELETE' }); load(); };

  const toggle = document.createElement('span');
  toggle.className = 'toggle';
  toggle.setAttribute('role', 'checkbox');
  toggle.setAttribute('aria-checked', t.done ? 'true' : 'false');
  toggle.setAttribute('aria-label', t.title);
  toggle.setAttribute('tabindex', '0');
  const doToggle = async () => {
    await api(`/api/todos/${t.id}/done`, jsonOpts('POST', { done: !t.done }));
    load();
  };
  toggle.onclick = doToggle;
  toggle.onkeydown = e => {
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); doToggle(); }
  };

  li.append(time, title, del, toggle);
  return li;
}

async function add() {
  const ti = document.getElementById('title');
  const title = ti.value.trim();
  if (!title) return;
  const time = document.getElementById('time').value;
  await api('/api/todos', jsonOpts('POST', { title, date: DATE, remind_at: time || null }));
  ti.value = '';
  document.getElementById('time').value = '';
  ti.focus();
  load();
}

document.getElementById('add').onclick = add;
document.getElementById('title').addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
load();
