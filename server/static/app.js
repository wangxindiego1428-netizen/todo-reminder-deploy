function todayStr() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
const DATE = todayStr();
document.getElementById('today').textContent = `${new Date().getMonth() + 1}/${new Date().getDate()}`;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = '/login'; return null; }
  return r.json();
}

async function load() {
  const data = await api(`/api/todos?date=${DATE}`);
  if (!data) return;
  const list = document.getElementById('list');
  list.innerHTML = '';
  document.getElementById('empty').hidden = data.todos.length > 0;
  for (const t of data.todos) list.appendChild(renderItem(t));
}

function renderItem(t) {
  const li = document.createElement('li');
  li.className = t.done ? 'item done' : 'item';
  const cb = document.createElement('input');
  cb.type = 'checkbox'; cb.checked = !!t.done;
  cb.onchange = async () => { await api(`/api/todos/${t.id}/done`, jsonOpts('POST', {done: cb.checked})); load(); };
  const span = document.createElement('span');
  span.className = 'title';
  const time = t.remind_at ? `${t.remind_at} ` : '';
  const tail = t.rolled_from ? ' （往日遗留）' : '';
  span.textContent = `${time}${t.title}${tail}`;
  const del = document.createElement('button');
  del.className = 'del'; del.textContent = '✕';
  del.onclick = async () => { await api(`/api/todos/${t.id}`, {method: 'DELETE'}); load(); };
  li.append(cb, span, del);
  return li;
}

function jsonOpts(method, body) {
  return { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) };
}

async function add() {
  const title = document.getElementById('title').value.trim();
  if (!title) return;
  const time = document.getElementById('time').value;
  await api('/api/todos', jsonOpts('POST', {title, date: DATE, remind_at: time || null}));
  document.getElementById('title').value = '';
  document.getElementById('time').value = '';
  load();
}

document.getElementById('add').onclick = add;
document.getElementById('title').addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
load();
