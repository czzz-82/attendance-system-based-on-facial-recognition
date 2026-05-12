/* 合照识别：上传 + 当前结果展示 + 历史完整分析档案 */
app.chartTheme?.();
const groupColors = app.chartPalette ? app.chartPalette() : ['#4de3ff', '#54e39a', '#ffb84d', '#ff6b7a', '#8fa2ff', '#31d0aa', '#9fb6ca'];
const form = document.getElementById('groupForm');
const msg = document.getElementById('groupMsg');
const resultPanel = document.getElementById('resultPanel');
const comparePanel = document.getElementById('comparePanel');
const matchedTbody = document.getElementById('matchedTbody');
const actTbody = document.querySelector('#actTable tbody');
const photoInput = document.getElementById('groupPhotoInput');
const originalPreview = document.getElementById('originalPreview');
const submitBtn = document.getElementById('groupSubmitBtn');
const srPanel = document.getElementById('srPanel');
const srSamples = document.getElementById('srSamples');
const srHint = document.getElementById('srHint');
const historyAnalysisPanel = document.getElementById('historyAnalysisPanel');
const historyAnalysisContent = document.getElementById('historyAnalysisContent');
const historyAnalysisMeta = document.getElementById('historyAnalysisMeta');

document.querySelector('input[name="held_on"]').valueAsDate = new Date();
let pieChart = null;
let originalDataUrl = '';

photoInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  originalDataUrl = await app.fileToDataUrl(file);
  originalPreview.src = originalDataUrl;
  comparePanel.classList.remove('hide');
  document.getElementById('annotatedImg').removeAttribute('src');
  srPanel.classList.add('hide');
  srSamples.innerHTML = '';
  msg.className = 'msg';
  msg.textContent = `已选择：${file.name}（${(file.size / 1024 / 1024).toFixed(2)} MB）`;
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  msg.className = 'msg';
  msg.innerHTML = '<span class="spinner"></span> 正在识别并保存分析档案：检测人脸 → 小脸超分 → 特征匹配 → 情绪分析 → 归档...';
  submitBtn.disabled = true;
  const fd = new FormData(form);
  try {
    const r = await app.api('/api/group/upload', { method: 'POST', body: fd });
    if (!r) return;
    const j = await r.json();
    if (!j.ok) {
      msg.className = 'msg err';
      msg.textContent = '✗ ' + (j.error || '失败');
      return;
    }
    msg.className = 'msg ok';
    msg.textContent = `✓ 检测 ${j.detected} 张人脸，匹配 ${j.matched} 名学生；已保存原图、标注图、超分对比和识别结果。`;

    comparePanel.classList.remove('hide');
    resultPanel.classList.remove('hide');
    originalPreview.src = originalDataUrl || `/static/${j.original}?t=${Date.now()}`;
    document.getElementById('annotatedImg').src = `/static/${j.annotated}?t=${Date.now()}`;
    document.getElementById('detectedCnt').textContent = j.detected ?? 0;
    document.getElementById('matchedCnt').textContent = j.matched ?? 0;
    document.getElementById('unmatchedCnt').textContent = j.unmatched ?? Math.max(0, (j.detected || 0) - (j.matched || 0));
    matchedTbody.innerHTML = renderStudentsRows(j.students || []);

    drawEmotionPie(j.emotions?.cn || {});
    renderSrSamples(j.sr_samples || [], j.sr_triggered || 0, srSamples, srPanel, srHint);
    loadActivities();
  } finally {
    submitBtn.disabled = false;
  }
});

function renderStudentsRows(students) {
  return students.length ? students.map(s => `
    <tr>
      <td>${app.escapeHtml(s.student_no)}</td>
      <td>${app.escapeHtml(s.name)}</td>
      <td>${app.escapeHtml(s.emotion_cn || s.emotion || '-')}</td>
      <td>${s.distance ?? '-'}</td>
    </tr>`).join('') : '<tr><td colspan="4" class="muted">暂未匹配到学生，请检查学生库或合照清晰度。</td></tr>';
}

function renderSrSamples(samples, triggeredCount, target = srSamples, panel = srPanel, hint = srHint) {
  if (!samples.length) {
    panel.classList.add('hide');
    target.innerHTML = '';
    return;
  }
  panel.classList.remove('hide');
  if (hint) {
    hint.textContent = triggeredCount > 0
      ? `本次有 ${triggeredCount} 张人脸尺寸低于阈值，实际触发小脸超分；下方展示最多 ${samples.length} 组局部对比。`
      : '本次检测到的人脸尺寸均未低于阈值，下方为最小人脸的超分演示对比。';
  }
  target.innerHTML = samples.map((s, idx) => `
    <div class="sr-card">
      <div class="sr-card-head">
        <b>#${idx + 1} ${s.triggered ? '实际触发超分' : '演示增强'}</b>
        <span>原人脸 ${app.escapeHtml(s.face_size || '-')}</span>
      </div>
      <div class="sr-pair">
        <figure>
          <img src="/static/${s.before}?t=${Date.now()}" alt="超分前" />
          <figcaption>Before 裁剪小脸</figcaption>
        </figure>
        <figure>
          <img src="/static/${s.after}?t=${Date.now()}" alt="超分后" />
          <figcaption>After GFPGAN 超分</figcaption>
        </figure>
      </div>
    </div>`).join('');
}

function drawEmotionPie(data) {
  const labels = Object.keys(data);
  const counts = Object.values(data);
  if (pieChart) pieChart.destroy();
  if (!labels.length) {
    const ctx = document.getElementById('emotionPie').getContext('2d');
    ctx.clearRect(0, 0, 400, 220);
    return;
  }
  pieChart = new Chart(document.getElementById('emotionPie'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data: counts, backgroundColor: groupColors }] },
    options: { plugins: { legend: { position: 'right' } }, cutout: '58%' }
  });
}

async function loadActivities() {
  const r = await app.api('/api/group/activities');
  if (!r) return;
  const j = await r.json();
  const items = j.items || [];
  if (!items.length) {
    actTbody.innerHTML = '<tr><td colspan="7" class="muted">暂无历史活动</td></tr>';
    return;
  }
  actTbody.innerHTML = items.map(a => {
    const rate = a.detected ? Math.round((a.matched || 0) * 100 / a.detected) : 0;
    const analysisBtn = `<button class="btn-mini analysisBtn" data-id="${a.id}">${a.has_analysis ? '查看分析' : '旧版详情'}</button>`;
    return `<tr>
      <td>${app.escapeHtml(a.held_on)}</td>
      <td>${app.escapeHtml(a.name)}</td>
      <td>${a.detected ?? 0}</td>
      <td>${a.matched ?? 0}</td>
      <td><span class="tag ${rate >= 80 ? 'ok' : rate >= 50 ? 'warn' : 'fail'}">${rate}%</span></td>
      <td><a href="/static/${a.photo_path}" target="_blank">标注图</a></td>
      <td>${analysisBtn}</td>
    </tr>`;
  }).join('');
  actTbody.querySelectorAll('.analysisBtn').forEach(btn => {
    btn.addEventListener('click', () => loadActivityAnalysis(btn.dataset.id));
  });
}

async function loadActivityAnalysis(id) {
  const r = await app.api(`/api/group/activities/${id}`);
  if (!r) return;
  const j = await r.json();
  if (j.error) { app.toast(j.error, 'err'); return; }
  const a = j.analysis || {};
  historyAnalysisPanel.classList.remove('hide');
  historyAnalysisMeta.textContent = `${a.activity_name || j.activity?.name || '未命名活动'} · ${a.held_on || '-'} · 检测 ${a.detected ?? 0} 人 / 匹配 ${a.matched ?? 0} 人`;
  historyAnalysisContent.innerHTML = renderAnalysisArchive(a);
  const srBox = historyAnalysisContent.querySelector('[data-sr-archive]');
  const srArchivePanel = historyAnalysisContent.querySelector('[data-sr-panel]');
  const srArchiveHint = historyAnalysisContent.querySelector('[data-sr-hint]');
  renderSrSamples(a.sr_samples || [], a.sr_triggered || 0, srBox, srArchivePanel, srArchiveHint);
  historyAnalysisPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderAnalysisArchive(a) {
  const emotionItems = Object.entries(a.emotions?.cn || {});
  const unmatched = a.unmatched_faces || [];
  return `
    <div class="analysis-archive-grid">
      <div class="compare-card">
        <div class="compare-title">原始合照</div>
        ${a.original ? `<img src="/static/${a.original}" alt="原始合照" />` : '<div class="archive-empty">旧记录未保存原始图</div>'}
      </div>
      <div class="compare-card">
        <div class="compare-title">识别标注图</div>
        ${a.annotated ? `<img src="/static/${a.annotated}" alt="识别标注图" />` : '<div class="archive-empty">无标注图</div>'}
      </div>
    </div>
    <div class="archive-metrics">
      <span class="metric">检测 <b>${a.detected ?? 0}</b> 人</span>
      <span class="metric">匹配 <b>${a.matched ?? 0}</b> 人</span>
      <span class="metric">未匹配 <b>${a.unmatched ?? 0}</b> 人</span>
      <span class="metric">超分触发 <b>${a.sr_triggered ?? '-'}</b> 人</span>
      <span class="metric">阈值 <b>${a.match_threshold ?? '-'}</b></span>
    </div>
    <section class="archive-block" data-sr-panel>
      <div class="section-head"><h3>保存的超分局部对比</h3><span class="hint" data-sr-hint></span></div>
      <div class="sr-samples" data-sr-archive></div>
    </section>
    <div class="layout-2col archive-detail-layout">
      <section class="archive-block">
        <h3>识别名单</h3>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>学号</th><th>姓名</th><th>情绪</th><th>距离</th><th>超分</th></tr></thead>
          <tbody>${renderArchiveStudents(a.students || [])}</tbody>
        </table></div>
      </section>
      <section class="archive-block">
        <h3>情绪与未匹配分析</h3>
        <div class="emotion-list">${emotionItems.length ? emotionItems.map(([k,v]) => `<span class="metric">${app.escapeHtml(k)} <b>${v}</b></span>`).join('') : '<span class="muted">暂无情绪数据</span>'}</div>
        <div class="unmatched-list">${unmatched.length ? unmatched.map(u => `<div class="unmatched-item">#${u.index} ${app.escapeHtml(u.reason || '未匹配')} <span>${app.escapeHtml(u.face_size || '')}</span></div>`).join('') : '<div class="muted">无未匹配详情</div>'}</div>
      </section>
    </div>`;
}

function renderArchiveStudents(students) {
  return students.length ? students.map(s => `<tr>
    <td>${app.escapeHtml(s.student_no || '-')}</td>
    <td>${app.escapeHtml(s.name || '-')}</td>
    <td>${app.escapeHtml(s.emotion_cn || s.emotion || '-')}</td>
    <td>${s.distance ?? '-'}</td>
    <td>${s.sr_triggered ? '<span class="tag warn">是</span>' : '<span class="tag ok">否</span>'}</td>
  </tr>`).join('') : '<tr><td colspan="5" class="muted">无识别名单</td></tr>';
}

document.getElementById('reloadActivitiesBtn').addEventListener('click', loadActivities);
document.getElementById('closeHistoryAnalysisBtn').addEventListener('click', () => historyAnalysisPanel.classList.add('hide'));
loadActivities();
