/* 考勤记录：筛选查询 */
const form = document.getElementById('filterForm');
const tbody = document.querySelector('#recordsTable tbody');

async function load() {
  const fd = new FormData(form);
  const params = new URLSearchParams();
  for (const [k, v] of fd.entries()) {
    if (v) params.append(k, v);
  }
  const r = await app.api('/api/attendance/records?' + params.toString());
  if (!r) return;
  const j = await r.json();
  tbody.innerHTML = (j.items || []).map(it => {
    const tag = it.status === 'success'
      ? '<span class="tag ok">成功</span>'
      : it.status === 'fail'
      ? '<span class="tag fail">活体未通过</span>'
      : '<span class="tag warn">未识别</span>';
    return `<tr>
      <td>${it.timestamp}</td>
      <td>${app.escapeHtml(it.student_no || '-')}</td>
      <td>${app.escapeHtml(it.name || '-')}</td>
      <td>${tag}</td>
      <td>${it.liveness_passed ? '✓' : '✗'}</td>
      <td>${app.escapeHtml(it.emotion_cn || '-')}</td>
      <td class="muted">${app.escapeHtml(it.note || '')}</td>
    </tr>`;
  }).join('');
}

form.addEventListener('submit', (e) => { e.preventDefault(); load(); });
load();
