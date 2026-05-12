// 通用：DOM 工具、退出登录、fetch 包装、Toast
const $ = (s, p = document) => p.querySelector(s);
const $$ = (s, p = document) => Array.from(p.querySelectorAll(s));

const logoutBtn = document.getElementById('logoutBtn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    location.href = '/login';
  });
}

function toast(message, type = 'info', timeout = 2400) {
  const el = document.getElementById('toast');
  if (!el) return alert(message);
  el.textContent = message;
  el.className = `toast ${type}`;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.add('hide'), timeout);
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = '/login'; return null; }
  if (r.status === 403) toast('权限不足：该操作需要教师权限', 'err');
  return r;
}

function fmtTime(ts) {
  return ts ? ts.replace('T', ' ') : '-';
}

function escapeHtml(s) {
  return (s ?? '').toString().replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function statusTag(status) {
  if (status === 'success') return '<span class="tag ok">成功</span>';
  if (status === 'fail') return '<span class="tag fail">活体未通过</span>';
  return '<span class="tag warn">未识别</span>';
}

window.app = { api, fmtTime, escapeHtml, toast, fileToDataUrl, statusTag };


function applyChartTheme() {
  if (!window.Chart) return;
  Chart.defaults.color = '#a9c6dc';
  Chart.defaults.font.family = 'Cascadia Code, Microsoft YaHei UI, PingFang SC, sans-serif';
  Chart.defaults.borderColor = 'rgba(126, 214, 255, .14)';
  Chart.defaults.plugins.tooltip = {
    ...Chart.defaults.plugins.tooltip,
    backgroundColor: 'rgba(4, 12, 23, .94)',
    titleColor: '#e7f4ff',
    bodyColor: '#cfe8f8',
    borderColor: 'rgba(77, 227, 255, .32)',
    borderWidth: 1,
    padding: 12,
    displayColors: true,
  };
  Chart.defaults.plugins.legend.labels = {
    ...Chart.defaults.plugins.legend.labels,
    color: '#a9c6dc',
    usePointStyle: true,
    boxWidth: 9,
    boxHeight: 9,
  };
}
function chartPalette() {
  return ['#4de3ff', '#54e39a', '#ffb84d', '#ff6b7a', '#8fa2ff', '#31d0aa', '#9fb6ca'];
}
window.app.chartTheme = applyChartTheme;
window.app.chartPalette = chartPalette;
applyChartTheme();
