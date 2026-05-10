/* 考勤打卡：摄像头 + 活体挑战 + 提交识别 */
const video = document.getElementById('video');
const overlay = document.getElementById('overlay');
const startBtn = document.getElementById('startBtn');
const captureBtn = document.getElementById('captureBtn');
const challengeArea = document.getElementById('challengeArea');
const resultCard = document.getElementById('resultCard');
const recentTbody = document.querySelector('#recentTable tbody');

let stream = null;

startBtn.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    overlay.width = video.videoWidth;
    overlay.height = video.videoHeight;
    captureBtn.disabled = false;
    startBtn.disabled = true;
    startBtn.textContent = '✓ 摄像头已开启';
  } catch (err) {
    alert('无法访问摄像头：' + err.message + '\n请确认浏览器权限或使用 https/localhost。');
  }
});

captureBtn.addEventListener('click', startAttendance);

async function startAttendance() {
  resultCard.classList.add('hide');
  resultCard.className = 'result-card hide';
  captureBtn.disabled = true;

  // 1. 申请挑战
  const r = await app.api('/api/attendance/challenge', { method: 'POST' });
  const data = await r.json();
  const { token, challenges, instructions } = data;

  challengeArea.innerHTML = challenges.map((c, i) => `
    <div class="challenge" data-action="${c}">
      <div class="step">动作 ${i + 1}：${instructions[i]}</div>
      <div class="status">⏳ 等待执行...</div>
    </div>`).join('');

  // 2. 倒计时 + 采集帧（共 5 秒，每 200ms 采一帧 → 25 帧）
  const total = 5000;
  const interval = 180;
  const frames = [];
  const startTs = Date.now();
  const cap = document.createElement('canvas');
  cap.width = video.videoWidth; cap.height = video.videoHeight;
  const ctx = cap.getContext('2d');

  challengeArea.insertAdjacentHTML('beforeend',
    `<div class="progress"><div id="progBar" style="width:0%"></div></div>
     <div id="countdown" class="muted">采集中... 0%</div>`);
  const bar = document.getElementById('progBar');
  const cd = document.getElementById('countdown');

  const timerId = setInterval(() => {
    ctx.drawImage(video, 0, 0);
    frames.push(cap.toDataURL('image/jpeg', 0.6));
    const elapsed = Date.now() - startTs;
    const pct = Math.min(100, (elapsed / total) * 100);
    bar.style.width = pct + '%';
    cd.textContent = `采集中... ${Math.floor(pct)}% （已 ${frames.length} 帧）`;
    if (elapsed >= total) {
      clearInterval(timerId);
      submitFrames(token, frames, challenges);
    }
  }, interval);
}

async function submitFrames(token, frames, challenges) {
  $('#countdown').textContent = '上传并校验中...';
  const r = await app.api('/api/attendance/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, frames }),
  });
  if (!r) return;
  const j = await r.json();

  // 更新挑战状态
  $$('.challenge').forEach(div => {
    const a = div.dataset.action;
    if (!a) return;
    const ok = j.actions_result?.[a];
    const st = div.querySelector('.status');
    if (ok) { st.innerHTML = '<span class="status-ok">✓ 已识别</span>'; }
    else { st.innerHTML = '<span class="status-fail">✗ 未识别到</span>'; }
  });

  // 结果卡
  resultCard.classList.remove('hide');
  if (j.status === 'success') {
    resultCard.classList.add('success');
    resultCard.innerHTML = `
      <div class="tag ok">✓ 考勤成功</div>
      <div class="name" style="margin-top:8px">${app.escapeHtml(j.matched_student.name)}（${app.escapeHtml(j.matched_student.student_no)}）</div>
      <div class="meta">${j.timestamp}</div>
      <div class="meta">情绪：${app.escapeHtml(j.emotion_cn || j.emotion)}
                       人脸距离：${j.distance ?? '-'}</div>`;
  } else if (j.status === 'fail') {
    resultCard.classList.add('fail');
    resultCard.innerHTML = `
      <div class="tag fail">✗ 活体检测未通过</div>
      <div class="meta" style="margin-top:6px">未完成所有动作挑战，可能是照片或视频伪造。请重试。</div>`;
  } else {
    resultCard.classList.add('fail');
    resultCard.innerHTML = `
      <div class="tag warn">⚠ 未匹配到学生</div>
      <div class="meta" style="margin-top:6px">活体已通过但人脸未匹配到库中学生。</div>`;
  }

  captureBtn.disabled = false;
  loadRecent();
}

async function loadRecent() {
  const r = await app.api('/api/attendance/records?');
  if (!r) return;
  const j = await r.json();
  const items = (j.items || []).slice(0, 8);
  recentTbody.innerHTML = items.map(it => {
    const tag = it.status === 'success'
      ? '<span class="tag ok">成功</span>'
      : it.status === 'fail'
      ? '<span class="tag fail">活体未过</span>'
      : '<span class="tag warn">未识别</span>';
    return `<tr>
      <td>${it.timestamp}</td>
      <td>${app.escapeHtml(it.student_no || '-')}</td>
      <td>${app.escapeHtml(it.name || '-')}</td>
      <td>${tag}</td>
      <td>${it.liveness_passed ? '✓' : '✗'}</td>
      <td>${app.escapeHtml(it.emotion_cn || '-')}</td>
    </tr>`;
  }).join('');
}

loadRecent();
