/* 统计图表 */
const colors = ['#5878ff', '#58c878', '#ffb84d', '#ec6868', '#9b66ff', '#33c4d4', '#9099ad'];

(async function() {
  // 活动参与频次（柱状图）
  const r1 = await fetch('/api/stats/activities');
  const j1 = await r1.json();
  const items = (j1.items || []).slice(0, 30);
  new Chart(document.getElementById('activityBar'), {
    type: 'bar',
    data: {
      labels: items.map(i => i.name),
      datasets: [{ label: '参与次数', data: items.map(i => i.cnt), backgroundColor: '#5878ff' }]
    },
    options: { plugins: { legend: { display: false } },
               scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
  });
  document.querySelector('#actTable tbody').innerHTML =
    (j1.items || []).map(i => `<tr>
      <td>${app.escapeHtml(i.student_no)}</td>
      <td>${app.escapeHtml(i.name)}</td>
      <td>${i.cnt}</td></tr>`).join('');

  // 情绪饼图
  const r2 = await fetch('/api/stats/emotions');
  const j2 = await r2.json();
  new Chart(document.getElementById('emotionPie'), {
    type: 'doughnut',
    data: {
      labels: (j2.items || []).map(i => i.label),
      datasets: [{ data: (j2.items || []).map(i => i.count), backgroundColor: colors }]
    },
    options: { plugins: { legend: { position: 'right' } } }
  });

  // 情绪时间线（折线图）
  const r3 = await fetch('/api/stats/emotions/timeline');
  const j3 = await r3.json();
  const items3 = j3.items || [];
  const days = [...new Set(items3.map(i => i.d))].sort();
  const emotions = [...new Set(items3.map(i => i.emotion))];
  const map = {};
  for (const it of items3) {
    map[it.emotion] = map[it.emotion] || {};
    map[it.emotion][it.d] = it.cnt;
  }
  const datasets = emotions.map((e, idx) => ({
    label: e, borderColor: colors[idx % colors.length],
    backgroundColor: colors[idx % colors.length] + '33', tension: 0.25,
    data: days.map(d => map[e][d] || 0),
  }));
  new Chart(document.getElementById('emotionLine'), {
    type: 'line',
    data: { labels: days, datasets },
    options: { responsive: true, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
  });
})();
