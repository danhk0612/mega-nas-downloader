async function loadStatus() {
  const response = await fetch("/api/status");
  if (!response.ok) {
    throw new Error(`status request failed: ${response.status}`);
  }
  return response.json();
}

async function loadJobs() {
  const response = await fetch("/api/jobs");
  if (!response.ok) {
    throw new Error(`jobs request failed: ${response.status}`);
  }
  return response.json();
}

async function createJob(payload) {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error?.message || `job create failed: ${response.status}`);
  }
  return body;
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

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatStatus(status) {
  const labels = {
    pending: "대기",
    running: "다운로드 중",
    completed: "완료",
    failed: "실패",
    canceled: "취소됨",
  };
  return labels[status] || status;
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

function setJobs(jobs) {
  const target = document.querySelector("#jobs");
  if (!jobs.length) {
    target.innerHTML = '<p class="empty">등록된 작업이 없습니다.</p>';
    return;
  }
  target.innerHTML = jobs
    .map(
      (job) => `
        <article class="job-card">
          <div>
            <strong>${escapeHtml(job.name || job.mega_url_masked || `작업 #${job.id}`)}</strong>
            <span>${escapeHtml(job.mega_url_masked || "")}</span>
          </div>
          <div class="job-meta">
            <span>${formatStatus(job.status)}</span>
            <span>등록 ${formatDate(job.registered_at)}</span>
            <span>대상 ${escapeHtml(job.subfolder || "/")}</span>
          </div>
          ${
            job.error_message
              ? `<p class="job-error">${escapeHtml(job.error_message)}</p>`
              : ""
          }
        </article>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
    const { jobs } = await loadJobs();
    setSummary(status);
    setJobs(jobs);
    setDiagnostics(status);
    badge.textContent = status.megacmd.ok ? "정상" : "경고";
    badge.className = `badge ${status.megacmd.ok ? "ok" : "bad"}`;
  } catch (error) {
    badge.textContent = "오류";
    badge.className = "badge bad";
  }
}

document.querySelector("#downloadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.querySelector("#formMessage");
  message.textContent = "등록 중...";
  try {
    await createJob({
      mega_url: document.querySelector("#megaUrl").value,
      name: document.querySelector("#jobName").value,
      subfolder: document.querySelector("#subfolder").value,
    });
    event.target.reset();
    message.textContent = "작업을 등록했습니다.";
    await refresh();
  } catch (error) {
    message.textContent = error.message;
  }
});

refresh();
setInterval(refresh, 5000);
