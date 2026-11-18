/** File System Access 기반 관제 뷰어 — 5초 폴링 */

import { parseIni, statusFromIni, tokensFromJson } from "./ini.js";
import {
  supportsFsAccess,
  pickDataDirectory,
  loadDirHandle,
  clearDirHandle,
  ensurePermission,
  readTextFile,
} from "./fs.js";

const POLL_MS = 5000;
const $ = (id) => document.getElementById(id);

let dirHandle = null;
let countdown = 5;
let selectedId = null;
let timer = null;

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function agentBar(pct, kind) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return `<div class="bar-single ${kind}"><span style="width:${p}%"></span></div>
    <div style="text-align:right;font-size:11px;color:#94a3b8;margin-top:2px">${p}%</div>`;
}

function renderCategoryBars(elId, mapping, kind) {
  const el = $(elId);
  const entries = Object.entries(mapping || {});
  el.innerHTML = entries.length
    ? entries
        .map(
          ([name, pct]) =>
            `<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span>${name}</span><span>${pct}%</span></div>${agentBar(pct, kind)}</div>`
        )
        .join("")
    : `<p class="muted">카테고리 없음</p>`;
}

function setWarning(msg) {
  const w = $("warning");
  if (!msg) {
    w.classList.add("hidden");
    w.textContent = "";
    return;
  }
  w.textContent = msg;
  w.classList.remove("hidden");
}

function showMain(connected) {
  $("gate").classList.toggle("hidden", connected);
  if (connected) {
    $("mainDash").classList.remove("hidden");
    $("mainDash").style.display = "grid";
  } else {
    $("mainDash").classList.add("hidden");
    $("mainDash").style.display = "none";
  }
}

function renderState(data, tokens) {
  const overall = data.meta?.overall_progress ?? 0;
  const projectName = (data.meta?.project_name || "").trim() || "—";
  $("projectTitle").textContent = projectName;
  $("projectMeta").textContent = `전체 ${data.meta?.total_tasks ?? "—"}항목 · 평균 ${overall}% · GitHub Pages 콘솔`;
  document.title = `${projectName} · Central-Agent`;
  $("overallPct").textContent = `${overall}%`;

  renderCategoryBars("categoryBarsCursor", data.category_progress_cursor, "cursor");
  renderCategoryBars("categoryBarsGrok", data.category_progress_grok, "grok");

  $("statusCounts").innerHTML = Object.entries(data.status_counts || {})
    .map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`)
    .join("");

  $("agentStatus").innerHTML = `
    <div><span>mode</span><span class="accent">File System</span></div>
    <div><span>poll</span><span class="on">5s</span></div>
  `;

  if (tokens) {
    $("tokenBox").classList.remove("hidden");
    $("tokenUsedPct").textContent = `${tokens.used_pct}%`;
    $("tokenCursorPct").textContent = `${tokens.cursor_pct}%`;
    $("tokenGrokPct").textContent = `${tokens.grok_pct}%`;
    $("tokenPlan").textContent = tokens.plan;
  } else {
    $("tokenBox").classList.add("hidden");
  }

  const items = data.items || [];
  $("itemTable").innerHTML = items
    .map(
      (i) => `<tr data-id="${i.req_id}" class="${selectedId === i.req_id ? "active" : ""}">
      <td class="mono">${i.req_id}</td>
      <td>${i.title}</td>
      <td>${badge(i.status)}</td>
      <td class="num">${i.progress}</td>
      <td>${badge(i.qa_status)}</td>
      <td class="num">${i.qa_score}</td>
      <td class="num">${i.qa_rework_count}</td>
    </tr>`
    )
    .join("");

  $("itemTable").querySelectorAll("tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", () => {
      selectedId = tr.dataset.id;
      const item = items.find((x) => x.req_id === selectedId);
      renderDetail(item);
      renderState(data, tokens);
    });
  });

  if (selectedId) {
    renderDetail(items.find((x) => x.req_id === selectedId));
  }
}

function renderDetail(item) {
  if (!item) {
    $("itemDetail").textContent = "항목을 선택하세요.";
    return;
  }
  $("itemDetail").innerHTML = `
    <div><span class="muted">ID</span> ${item.req_id}</div>
    <div><span class="muted">제목</span> ${item.title}</div>
    <div><span class="muted">category</span> ${item.category}</div>
    <div><span class="muted">dev_note</span> ${item.dev_note || "—"}</div>
    <div><span class="muted">qa_diff_note</span> ${item.qa_diff_note || "—"}</div>
    <div><span class="muted">갱신</span> ${item.last_updated_by} @ ${item.last_updated_at}</div>
  `;
}

async function refreshFromFs() {
  if (!dirHandle) return;
  const ok = await ensurePermission(dirHandle);
  if (!ok) {
    setWarning("폴더 읽기 권한이 없습니다. 다시 선택해 주세요.");
    showMain(false);
    return;
  }

  const statusText = await readTextFile(dirHandle, "project_status.ini");
  if (statusText == null) {
    setWarning("project_status.ini 를 찾을 수 없습니다. 해당 프로젝트의 docs 폴더를 선택했는지 확인하세요.");
    return;
  }

  try {
    const sections = parseIni(statusText);
    const data = statusFromIni(sections);
    const tokenText = await readTextFile(dirHandle, "token_usage.json");
    const tokens = tokenText ? tokensFromJson(tokenText) : null;
    renderState(data, tokens);
    showMain(true);
    setWarning("");
    $("lastSync").textContent = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    $("folderLabel").textContent = dirHandle.name || "(선택됨)";
    countdown = 5;
  } catch (err) {
    setWarning("INI 파싱 실패: " + err);
  }
}

async function connectFolder() {
  if (!supportsFsAccess()) {
    setWarning("이 브라우저는 File System Access API를 지원하지 않습니다. Chrome/Edge를 사용하세요.");
    return;
  }
  try {
    dirHandle = await pickDataDirectory();
    await refreshFromFs();
    startPolling();
  } catch (err) {
    if (err && err.name === "AbortError") return;
    setWarning("폴더 선택 실패: " + err);
  }
}

async function disconnectFolder() {
  dirHandle = null;
  await clearDirHandle();
  stopPolling();
  showMain(false);
  $("projectTitle").textContent = "폴더를 선택하세요";
  $("folderLabel").textContent = "—";
  setWarning("");
}

function startPolling() {
  stopPolling();
  timer = setInterval(() => {
    refreshFromFs();
  }, POLL_MS);
}

function stopPolling() {
  if (timer) clearInterval(timer);
  timer = null;
}

async function boot() {
  $("btnPick").addEventListener("click", connectFolder);
  $("btnPick2").addEventListener("click", connectFolder);
  $("btnClear").addEventListener("click", disconnectFolder);

  setInterval(() => {
    countdown = Math.max(0, countdown - 1);
    $("countdown").textContent = String(countdown);
  }, 1000);

  if (!supportsFsAccess()) {
    setWarning("Chrome 또는 Edge에서 http://127.0.0.1:18766/ 로 열어 주세요. (file:// 불가)");
    return;
  }

  const saved = await loadDirHandle();
  if (saved && (await ensurePermission(saved))) {
    dirHandle = saved;
    await refreshFromFs();
    startPolling();
  } else {
    showMain(false);
  }
}

boot();
