/* 考勤记录：筛选查询 + 顶部统计 */
const form = document.getElementById('filterForm');
const tbody = document.querySelector('#recordsTable tbody');
const statsBox = document.getElementById('recordStats');

function renderRecordStats(items) {
  const total = items.length;
  const ok = items.filter(i => i.status === 'success').length;
  const fail = items.filter(i => i.status === 'fail').length;
  const unknown = items.filter(i => i.status === 'unknown').length;
  statsBox.innerHTML = `<span><b>${total}</b> 条</span><span><b>${ok}</b> 成功</span><span><b>${fail}</b> 活体失败</span><span><b>${unknown}</b> 未识别</span>`;
}

async function load() {
  const fd = new FormData(form);
  const params = new URLSearchParams();
  for (const [k, v] of fd.entries()) if (v) params.append(k, v);
  const r = await app.api('/api/attendance/records?' + params.toString());
  if (!r) return;
  const j = await r.json();
  const items = j.items || [];
  renderRecordStats(items);
  tbody.innerHTML = items.length ? items.map(it => `<tr>
      <td>${app.escapeHtml(it.timestamp)}</td>
      <td>${app.escapeHtml(it.student_no || '-')}</td>
      <td>${app.escapeHtml(it.name || '-')}</td>
      <td>${app.statusTag(it.status)}</td>
      <td>${it.liveness_passed ? '<span class="tag ok">通过</span>' : '<span class="tag fail">未过</span>'}</td>
      <td>${app.escapeHtml(it.emotion_cn || '-')}</td>
      <td class="muted note-cell" title="${app.escapeHtml(it.note || '')}">${app.escapeHtml(it.note || '')}</td>
    </tr>`).join('') : '<tr><td colspan="7" class="muted">暂无记录</td></tr>';
}

form.addEventListener('submit', (e) => { e.preventDefault(); load(); });
document.getElementById('resetFilterBtn').addEventListener('click', () => { form.reset(); load(); });
load();
