/* 学生管理：单个添加、批量导入、列表渲染 */
const studentsTbody = document.querySelector('#studentsTable tbody');

async function loadStudents() {
  const r = await app.api('/api/students');
  if (!r) return;
  const j = await r.json();
  studentsTbody.innerHTML = (j.items || []).map(s => `
    <tr data-id="${s.id}">
      <td>${s.photo_path ? `<img src="/static/${s.photo_path}" alt="" />` : '-'}</td>
      <td>${app.escapeHtml(s.student_no)}</td>
      <td>${app.escapeHtml(s.name)}</td>
      <td>${app.escapeHtml(s.class_name || '-')}</td>
      <td><button class="btn-link delBtn">删除</button></td>
    </tr>`).join('');

  studentsTbody.querySelectorAll('.delBtn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const tr = e.target.closest('tr');
      const id = tr.dataset.id;
      if (!confirm('确认删除该学生？')) return;
      const r = await app.api(`/api/students/${id}`, { method: 'DELETE' });
      const j = await r.json();
      if (j.ok) loadStudents();
      else alert(j.error || '删除失败');
    });
  });
}

document.getElementById('addForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const msg = document.getElementById('addMsg');
  msg.textContent = '上传中...';
  msg.className = 'msg';
  const r = await app.api('/api/students', { method: 'POST', body: fd });
  const j = await r.json();
  if (j.ok) {
    msg.className = 'msg ok';
    msg.textContent = '✓ 添加成功';
    e.target.reset();
    loadStudents();
  } else {
    msg.className = 'msg err';
    msg.textContent = '✗ ' + (j.error || '添加失败');
  }
});

document.getElementById('batchForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const files = e.target.photos.files;
  if (!files.length) return;
  const msg = document.getElementById('batchMsg');
  msg.textContent = `上传 ${files.length} 个文件中...`;
  const r = await app.api('/api/students/import', { method: 'POST', body: fd });
  const j = await r.json();
  msg.className = 'msg ok';
  msg.innerHTML = `成功：<b>${j.success.length}</b>，失败：<b>${j.failed.length}</b>`
    + (j.failed.length ? '<br>失败明细：<br>' + j.failed.map(f =>
       `<span class="muted">${app.escapeHtml(f.file)} → ${app.escapeHtml(f.reason)}</span>`).join('<br>') : '');
  loadStudents();
});

loadStudents();
