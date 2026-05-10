/* 合照识别：上传 + 渲染识别结果 + 历史活动列表 */
const form = document.getElementById('groupForm');
const msg = document.getElementById('groupMsg');
const resultPanel = document.getElementById('resultPanel');
const matchedTbody = document.getElementById('matchedTbody');
const actTbody = document.querySelector('#actTable tbody');

document.querySelector('input[name="held_on"]').valueAsDate = new Date();

let pieChart = null;

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  msg.className = 'msg'; msg.textContent = '识别中，请稍候...';
  const fd = new FormData(form);
  const r = await app.api('/api/group/upload', { method: 'POST', body: fd });
  if (!r) return;
  const j = await r.json();
  if (!j.ok) {
    msg.className = 'msg err';
    msg.textContent = '✗ ' + (j.error || '失败');
    return;
  }
  msg.className = 'msg ok';
  msg.textContent = `✓ 检测 ${j.detected} 张人脸，匹配 ${j.matched} 名学生`;

  resultPanel.classList.remove('hide');
  document.getElementById('annotatedImg').src = `/static/${j.annotated}?t=${Date.now()}`;
  document.getElementById('detectedCnt').textContent = j.detected;
  document.getElementById('matchedCnt').textContent = j.matched;
  matchedTbody.innerHTML = (j.students || []).map(s =>
    `<tr><td>${app.escapeHtml(s.student_no)}</td><td>${app.escapeHtml(s.name)}</td>
        <td>${app.escapeHtml(s.emotion_cn || s.emotion)}</td><td>${s.distance}</td></tr>`).join('');

  drawEmotionPie(j.emotions.cn || {});
  loadActivities();
});

function drawEmotionPie(data) {
  const labels = Object.keys(data);
  const counts = Object.values(data);
  if (pieChart) pieChart.destroy();
  pieChart = new Chart(document.getElementById('emotionPie'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: counts,
        backgroundColor: ['#5878ff', '#58c878', '#ffb84d', '#ec6868', '#9b66ff', '#33c4d4', '#9099ad'] }]
    },
    options: { plugins: { legend: { position: 'right' } } }
  });
}

async function loadActivities() {
  const r = await app.api('/api/group/activities');
  if (!r) return;
  const j = await r.json();
  actTbody.innerHTML = (j.items || []).map(a => `
    <tr>
      <td>${a.held_on}</td>
      <td>${app.escapeHtml(a.name)}</td>
      <td>${a.detected}</td>
      <td>${a.matched}</td>
      <td><a href="/static/${a.photo_path}" target="_blank">查看</a></td>
    </tr>`).join('');
}

loadActivities();
