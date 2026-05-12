/* 统计图表：综合参与、情绪分布、情绪趋势、考勤趋势 */
app.chartTheme?.();
const colors = app.chartPalette ? app.chartPalette() : ['#4de3ff', '#54e39a', '#ffb84d', '#ff6b7a', '#8fa2ff', '#31d0aa', '#9fb6ca'];
const statusColors = { success: '#54e39a', fail: '#ff6b7a', unknown: '#ffb84d' };
const statusLabels = { success: '成功', fail: '活体未通过', unknown: '未识别' };
let activityChart = null;
let emotionPieChart = null;
let emotionLineChart = null;
let attendanceLineChart = null;

function getFilterParams(includeSource = true) {
  const form = document.getElementById('emotionFilter');
  const params = new URLSearchParams();
  for (const [k, v] of new FormData(form).entries()) {
    if (!v) continue;
    if (!includeSource && k === 'source') continue;
    params.append(k, v);
  }
  return params;
}

function destroyChart(chart) {
  if (chart) chart.destroy();
}

function chartEmpty(canvas, text = '暂无数据') {
  const ctx = canvas.getContext('2d');
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, canvas.width || rect.width, canvas.height || rect.height);
  ctx.fillStyle = 'rgba(77, 227, 255, .08)';
  ctx.fillRect(0, 0, canvas.width || rect.width, canvas.height || rect.height);
  ctx.fillStyle = '#8ba7bd';
  ctx.font = '14px Microsoft YaHei UI, sans-serif';
  ctx.fillText(text, 18, 36);
}

function updateSummary({ participationItems = [], emotionItems = [], attendanceItems = [] }) {
  const box = document.getElementById('statsSummary');
  if (!box) return;
  const totalParticipation = participationItems.reduce((s, i) => s + Number(i.cnt || 0), 0);
  const attendanceSuccess = participationItems.reduce((s, i) => s + Number(i.attendance_cnt || 0), 0);
  const groupTotal = participationItems.reduce((s, i) => s + Number(i.group_cnt || 0), 0);
  const emotionTotal = emotionItems.reduce((s, i) => s + Number(i.count || 0), 0);
  box.innerHTML = `
    <span><b>${attendanceSuccess}</b> 次考勤成功</span>
    <span><b>${groupTotal}</b> 次合照参与</span>
    <span><b>${totalParticipation}</b> 综合参与</span>
    <span><b>${emotionTotal}</b> 条情绪记录</span>`;
}

async function loadActivitiesChart() {
  const r1 = await app.api('/api/stats/activities');
  if (!r1) return [];
  const j1 = await r1.json();
  const all = j1.items || [];
  const nonZero = all.filter(i => Number(i.cnt || 0) > 0);
  const items = (nonZero.length ? nonZero : all).slice(0, 30);

  destroyChart(activityChart);
  if (items.length) {
    activityChart = new Chart(document.getElementById('activityBar'), {
      type: 'bar',
      data: {
        labels: items.map(i => i.name),
        datasets: [
          { label: '考勤成功', data: items.map(i => i.attendance_cnt || 0), backgroundColor: '#5878ff', borderRadius: 8, stack: 'participation' },
          { label: '合照参与', data: items.map(i => i.group_cnt || 0), backgroundColor: '#33c4d4', borderRadius: 8, stack: 'participation' },
        ]
      },
      options: {
        plugins: { legend: { position: 'top' } },
        scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  } else chartEmpty(document.getElementById('activityBar'));

  document.querySelector('#actTable tbody').innerHTML = all.length
    ? all.map((i, idx) => `<tr>
        <td>${idx + 1}</td>
        <td>${app.escapeHtml(i.student_no)}</td>
        <td>${app.escapeHtml(i.name)}</td>
        <td>${i.attendance_cnt || 0}</td>
        <td>${i.group_cnt || 0}</td>
        <td><span class="tag ${(i.cnt || 0) > 0 ? 'ok' : 'warn'}">${i.cnt || 0}</span></td>
      </tr>`).join('')
    : '<tr><td colspan="6" class="muted">暂无学生数据</td></tr>';
  return all;
}

async function loadEmotionPie() {
  const params = getFilterParams(true);
  const r2 = await app.api('/api/stats/emotions?' + params.toString());
  if (!r2) return [];
  const j2 = await r2.json();
  const items = j2.items || [];
  destroyChart(emotionPieChart);
  if (items.length) {
    emotionPieChart = new Chart(document.getElementById('emotionPie'), {
      type: 'doughnut',
      data: { labels: items.map(i => i.label), datasets: [{ data: items.map(i => i.count), backgroundColor: colors }] },
      options: { plugins: { legend: { position: 'right' } }, cutout: '58%' }
    });
  } else chartEmpty(document.getElementById('emotionPie'));
  return items;
}

async function loadEmotionTimeline() {
  const params = getFilterParams(true);
  const r3 = await app.api('/api/stats/emotions/timeline?' + params.toString());
  if (!r3) return [];
  const j3 = await r3.json();
  const items = j3.items || [];
  const times = [...new Set(items.map(i => i.t))].sort();
  const emotions = [...new Set(items.map(i => i.label || i.emotion))];
  const map = {};
  for (const it of items) {
    const label = it.label || it.emotion;
    map[label] = map[label] || {};
    map[label][it.t] = it.cnt;
  }
  const datasets = emotions.map((e, idx) => ({
    label: e,
    borderColor: colors[idx % colors.length],
    backgroundColor: colors[idx % colors.length] + '33',
    tension: 0.25,
    pointRadius: 4,
    data: times.map(t => map[e][t] || 0),
  }));
  destroyChart(emotionLineChart);
  if (times.length) {
    emotionLineChart = new Chart(document.getElementById('emotionLine'), {
      type: 'line',
      data: { labels: times.map(t => t.slice(5)), datasets },
      options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });
  } else chartEmpty(document.getElementById('emotionLine'));
  return items;
}

async function loadAttendanceTimeline() {
  const params = getFilterParams(false);
  const r = await app.api('/api/stats/attendance/timeline?' + params.toString());
  if (!r) return [];
  const j = await r.json();
  const items = j.items || [];
  const times = [...new Set(items.map(i => i.t))].sort();
  const statuses = [...new Set(items.map(i => i.status))];
  const map = {};
  for (const it of items) {
    map[it.status] = map[it.status] || {};
    map[it.status][it.t] = it.cnt;
  }
  const datasets = statuses.map(s => ({
    label: statusLabels[s] || s,
    borderColor: statusColors[s] || '#9099ad',
    backgroundColor: (statusColors[s] || '#9099ad') + '33',
    tension: 0.25,
    pointRadius: 4,
    data: times.map(t => map[s][t] || 0),
  }));
  destroyChart(attendanceLineChart);
  if (times.length) {
    attendanceLineChart = new Chart(document.getElementById('attendanceLine'), {
      type: 'line',
      data: { labels: times.map(t => t.slice(5)), datasets },
      options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });
  } else chartEmpty(document.getElementById('attendanceLine'));
  return items;
}

async function loadAllStats() {
  const [participationItems, emotionItems, attendanceItems] = await Promise.all([
    loadActivitiesChart(),
    loadEmotionPie(),
    loadAttendanceTimeline(),
  ]);
  await loadEmotionTimeline();
  updateSummary({ participationItems, emotionItems, attendanceItems });
}

document.getElementById('emotionFilter').addEventListener('submit', (e) => { e.preventDefault(); loadAllStats(); });
document.getElementById('resetStatsBtn').addEventListener('click', () => { document.getElementById('emotionFilter').reset(); loadAllStats(); });
loadAllStats();
