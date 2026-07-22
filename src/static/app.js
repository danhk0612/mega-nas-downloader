async function loadStatus() {
  const response = await fetch("/api/status");
  if (!response.ok) {
    throw new Error(`status request failed: ${response.status}`);
  }
  return response.json();
}

function formatBytes(value) {
  if (value === null || value === undefined) return "확인 불가";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Number(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function setDiagnostics(status) {
  const rows = [
    ["앱 버전", status.app.version],
    ["시작 시각", status.app.started_at],
    ["MEGAcmd", status.megacmd.ok ? status.megacmd.version : status.megacmd.error],
    ["다운로드 폴더", status.paths.download_dir],
    ["다운로드 폴더 쓰기", status.paths.download_dir_writable.ok ? "가능" : status.paths.download_dir_writable.error],
    ["데이터 폴더", status.paths.data_dir],
    ["데이터 폴더 쓰기", status.paths.data_dir_writable.ok ? "가능" : status.paths.data_dir_writable.error],
    ["남은 용량", formatBytes(status.download_disk.free)],
  ];

  document.querySelector("#diagnostics").innerHTML = rows
    .map(([label, value]) => `<dt>${label}</dt><dd>${value || "확인 불가"}</dd>`)
    .join("");
}

function setSummary(status) {
  document.querySelector("#runningCount").textContent = status.jobs.running;
  document.querySelector("#pendingCount").textContent = status.jobs.pending;
  document.querySelector("#completedCount").textContent = status.jobs.completed;
  document.querySelector("#failedCount").textContent = status.jobs.failed;
}

async function refresh() {
  const badge = document.querySelector("#healthBadge");
  try {
    const status = await loadStatus();
    setSummary(status);
    setDiagnostics(status);
    badge.textContent = status.megacmd.ok ? "정상" : "경고";
    badge.className = `badge ${status.megacmd.ok ? "ok" : "bad"}`;
  } catch (error) {
    badge.textContent = "오류";
    badge.className = "badge bad";
  }
}

refresh();
setInterval(refresh, 5000);
