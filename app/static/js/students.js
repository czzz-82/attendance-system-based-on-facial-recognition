/* 学生管理：添加 / 编辑 / 删除 / 批量导入 / 本地预览 */
const studentsTbody = document.querySelector('#studentsTable tbody');
const form = document.getElementById('addForm');
const msg = document.getElementById('addMsg');
const formTitle = document.getElementById('formTitle');
const saveBtn = document.getElementById('saveBtn');
const cancelEditBtn = document.getElementById('cancelEditBtn');
const searchInput = document.getElementById('studentSearch');
const previewWrap = document.getElementById('studentPreviewWrap');
const previewImg = document.getElementById('studentPhotoPreview');
let allStudents = [];

function resetForm() {
  form.reset();
  form.elements.id.value = '';
  formTitle.textContent = '添加单个学生';
  saveBtn.textContent = '添加';
  cancelEditBtn.classList.add('hide');
  previewWrap.classList.add('hide');
  previewImg.removeAttribute('src');
  msg.textContent = '';
  msg.className = 'msg';
}

function renderStats(items) {
  const box = document.getElementById('studentStats');
  if (!box) return;
  const classes = new Set(items.map(i => i.class_name).filter(Boolean));
  box.innerHTML = `<span><b>${items.length}</b> 名学生</span><span><b>${classes.size}</b> 个班级</span>`;
}

function renderStudents(items) {
  if (!items.length) {
    studentsTbody.innerHTML = '<tr><td colspan="6" class="muted">暂无学生数据</td></tr>';
    return;
  }
  studentsTbody.innerHTML = items.map(s => `
    <tr data-id="${s.id}" data-no="${app.escapeHtml(s.student_no)}" data-name="${app.escapeHtml(s.name)}" data-class="${app.escapeHtml(s.class_name || '')}">
      <td>${s.id}</td>
      <td>${s.photo_path ? `<img class="avatar" src="/static/${s.photo_path}" alt="${app.escapeHtml(s.name)}" />` : '-'}</td>
      <td>${app.escapeHtml(s.student_no)}</td>
      <td>${app.escapeHtml(s.name)}</td>
      <td>${app.escapeHtml(s.class_name || '-')}</td>
      <td class="actions">
        <button class="btn-link editBtn">编辑</button>
        <button class="btn-link accountBtn">账号</button>
        <button class="btn-link danger delBtn">删除</button>
      </td>
    </tr>`).join('');

  $$('.editBtn', studentsTbody).forEach(btn => btn.addEventListener('click', (e) => {
    const tr = e.target.closest('tr');
    form.elements.id.value = tr.dataset.id;
    form.student_no.value = tr.dataset.no;
    form.name.value = tr.dataset.name;
    form.class_name.value = tr.dataset.class;
    formTitle.textContent = `编辑学生 #${tr.dataset.id}`;
    saveBtn.textContent = '保存修改';
    cancelEditBtn.classList.remove('hide');
    msg.className = 'msg';
    msg.textContent = '编辑模式：如需重建人脸特征，请重新上传照片；否则保持原照片和特征。';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }));

  $$('.accountBtn', studentsTbody).forEach(btn => btn.addEventListener('click', async (e) => {
    const id = e.target.closest('tr').dataset.id;
    const r = await app.api(`/api/students/${id}/account`, { method: 'POST' });
    if (!r) return;
    const j = await r.json();
    if (j.ok) alert(`学生账号已就绪\n用户名：${j.username}\n默认密码：${j.default_password}`);
    else app.toast(j.error || '账号创建失败（如果后端未启用该接口，可忽略）', 'err');
  }));

  $$('.delBtn', studentsTbody).forEach(btn => btn.addEventListener('click', async (e) => {
    const tr = e.target.closest('tr');
    if (!confirm(`确认删除学生 ${tr.dataset.name}（${tr.dataset.no}）？`)) return;
    const r = await app.api(`/api/students/${tr.dataset.id}`, { method: 'DELETE' });
    if (!r) return;
    const j = await r.json();
    if (j.ok) { app.toast('已删除学生', 'ok'); loadStudents(); }
    else app.toast(j.error || '删除失败', 'err');
  }));
}

function applySearch() {
  const q = (searchInput.value || '').trim().toLowerCase();
  const items = !q ? allStudents : allStudents.filter(s =>
    [s.student_no, s.name, s.class_name].some(v => (v || '').toLowerCase().includes(q))
  );
  renderStudents(items);
}

async function loadStudents() {
  const r = await app.api('/api/students');
  if (!r) return;
  const j = await r.json();
  allStudents = j.items || [];
  renderStats(allStudents);
  applySearch();
}

document.getElementById('studentPhotoInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) { previewWrap.classList.add('hide'); return; }
  previewImg.src = await app.fileToDataUrl(file);
  previewWrap.classList.remove('hide');
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(form);
  const id = form.elements.id.value;
  if (!id && !form.elements.photo.files.length) { app.toast('新增学生必须上传照片', 'err'); return; }
  msg.textContent = id ? '正在更新学生信息...' : '正在上传并提取人脸特征...';
  msg.className = 'msg';
  saveBtn.disabled = true;
  try {
    const r = await app.api(id ? `/api/students/${id}` : '/api/students', { method: id ? 'PUT' : 'POST', body: fd });
    if (!r) return;
    const j = await r.json();
    if (j.ok) {
      msg.className = 'msg ok';
      msg.textContent = id ? '✓ 修改成功' : '✓ 添加成功';
      app.toast(id ? '学生信息已更新' : '学生已加入人脸库', 'ok');
      resetForm();
      loadStudents();
    } else {
      msg.className = 'msg err';
      msg.textContent = '✗ ' + (j.error || '操作失败');
    }
  } finally {
    saveBtn.disabled = false;
  }
});

cancelEditBtn.addEventListener('click', resetForm);
searchInput.addEventListener('input', applySearch);
document.getElementById('reloadStudentsBtn').addEventListener('click', loadStudents);

document.getElementById('batchForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  if (!e.target.update_existing.checked) fd.set('update_existing', '0');
  const files = e.target.photos.files;
  if (!files.length) return;
  const batchMsg = document.getElementById('batchMsg');
  batchMsg.className = 'msg';
  batchMsg.textContent = `正在导入 ${files.length} 个文件，请稍候...`;
  const r = await app.api('/api/students/import', { method: 'POST', body: fd });
  if (!r) return;
  const j = await r.json();
  if (!j.ok) { batchMsg.className = 'msg err'; batchMsg.textContent = j.error || '导入失败'; return; }
  batchMsg.className = j.failed?.length ? 'msg err' : 'msg ok';
  batchMsg.innerHTML = `成功：<b>${(j.success || []).length}</b>，失败：<b>${(j.failed || []).length}</b>`
    + ((j.failed || []).length ? '<br>失败明细：<br>' + j.failed.map(f =>
       `<span class="muted">${app.escapeHtml(f.file)} → ${app.escapeHtml(f.reason)}</span>`).join('<br>') : '');
  loadStudents();
});

resetForm();
loadStudents();
