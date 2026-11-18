/** 관제 UI — 상태 5초 / 토큰 10초 폴링 */

const POLL_MS = 5000;
const TOKEN_POLL_MS = 10000;
let state = null;
let selectedId = null;
let countdown = 5;
let tokenCountdown = 10;

const $ = (id) => document.getElementById(id);

function formatPolledAt(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString("ko-KR", { hour12: false });
  } catch (_) {
    return iso;
  }
}

function renderTokens(tokens) {
  if (!tokens) return;
  $("tokenPlan").textContent = tokens.plan || "Premium";
  $("tokenWeekBadge").textContent = tokens.week_label || "—/4주차";
  $("tokenUsedPct").textContent = `${tokens.used_pct ?? 0}%`;
  $("tokenCursorPct").textContent = `${tokens.cursor_pct ?? 0}%`;
  $("tokenGrokPct").textContent = `${tokens.grok_pct ?? 0}%`;
  $("tokenLabel").textContent = tokens.label || "Weekly included usage";
  // 사용량 막대 (한도 대비, 합>100이면 축소)
  const c = Math.max(0, Number(tokens.cursor_pct) || 0);
  const g = Math.max(0, Number(tokens.grok_pct) || 0);
  const sum = c + g;
  const scale = sum > 100 ? 100 / sum : 1;
  $("tokenBarCursor").style.width = `${c * scale}%`;
  $("tokenBarGrok").style.width = `${g * scale}%`;

  // 구독 1~4주차
  const weeks = tokens.weeks || [];
  const track = $("tokenWeekTrack");
  const n = Math.max(1, Number(tokens.cycle_weeks) || weeks.length || 4);
  track.style.gridTemplateColumns = `repeat(${n}, 1fr)`;
  track.innerHTML = (weeks.length ? weeks : [1, 2, 3, 4].map((w) => ({ week: w, label: `${w}주차` })))
    .map((w) => {
      const cls = w.active ? "active" : w.done ? "done" : "";
      return `<div class="week-cell ${cls}">${w.label || w.week + "주차"}</div>`;
    })
    .join("");
  $("tokenWeekHint").textContent = Array.from({ length: n }, (_, i) => i + 1).join("/");

  // 다음 갱신 일자:시간 + 실제 사용 % 막대
  $("tokenRenewAt").textContent = tokens.renews_display || tokens.renews_at || "—";
  const usedPct = Math.max(0, Math.min(100, Number(tokens.used_pct) || 0));
  $("tokenUsedPctSmall").textContent = `${tokens.used_pct ?? 0}%`;
  $("tokenUsedFill").style.width = `${usedPct}%`;
  // 아주 작을 때도 보이도록 최소 표시(0%는 제외)
  if (usedPct > 0 && usedPct < 1.5) {
    $("tokenUsedFill").style.width = "1.5%";
  }
  $("tokenRemainText").textContent = tokens.remain_display || "—";
  $("tokenPolledAt").textContent = formatPolledAt(tokens.polled_at || tokens.updated_at);
  const src = tokens.source || "local";
  const liveOk = src === "cursor-live" && !tokens.live_error;
  $("tokenSourceLabel").textContent = liveOk
    ? "Cursor 자동 동기화"
    : tokens.live_error
      ? "동기화 실패(수동 가능)"
      : `출처:${src}`;
  const liveMsg = $("tokenLiveMsg");
  if (tokens.live_error) {
    liveMsg.textContent = String(tokens.live_error);
  } else if (tokens.live_display_message) {
    liveMsg.textContent = String(tokens.live_display_message);
  } else if (liveOk && Number(tokens.grok_pct || 0) === 0) {
    liveMsg.textContent = "통합 요금제: Cursor/Grok 공용 사용량 풀";
  } else {
    liveMsg.textContent = "";
  }
  const inp = $("tokenUsedInput");
  if (inp && document.activeElement !== inp) {
    inp.value = String(tokens.used_pct ?? 0);
  }
}

async function refreshTokens() {
  try {
    const res = await fetch(`/api/tokens?_=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return;
    renderTokens(await res.json());
    tokenCountdown = 10;
    $("tokenCountdown").textContent = String(tokenCountdown);
  } catch (_) {
    /* 상태 폴링 경고와 중복 표시 방지 */
  }
}

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function agentBar(pct, kind) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return `
    <div class="bar-single ${kind}"><span style="width:${p}%"></span></div>
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

function renderDashboard(data) {
  const overall = data.meta?.overall_progress ?? 0;
  $("overallPct").textContent = `${overall}%`;
  if (data.tokens) renderTokens(data.tokens);
  const projectName = (data.meta?.project_name || "").trim() || "—";
  $("projectTitle").textContent = projectName;
  $("projectMeta").textContent = `전체 ${data.meta?.total_tasks ?? "—"}항목 · 평균 ${overall}%`;
  document.title = `${projectName} · 관제`;

  // 하위 호환: 전용 키가 없으면 기존 category_progress 사용
  const cursorMap = data.category_progress_cursor || data.category_progress || {};
  const grokMap = data.category_progress_grok || {};
  renderCategoryBars("categoryBarsCursor", cursorMap, "cursor");
  renderCategoryBars("categoryBarsGrok", grokMap, "grok");

  $("statusCounts").innerHTML = Object.entries(data.status_counts || {})
    .map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`)
    .join("");

  $("agentStatus").innerHTML = Object.entries(data.agents || {})
    .map(([name, info]) => {
      const on = info.online;
      return `<div><span>${name}</span><span class="${on ? "on" : "off"}">${on ? "ONLINE" : "OFFLINE"}</span></div>`;
    })
    .join("");

  const m = data.metrics || {};
  const metricDefs = [
    ["첫 검증 합격률", m.first_pass_rate],
    ["평균 반려 횟수", m.avg_rework_count],
    ["자기보고 편차", m.self_report_deviation],
    ["판정 일관성", m.judgment_consistency],
    ["결함 적중률", m.defect_hit_rate],
    ["명령 응답(ms)", m.avg_command_ack_ms],
    ["요건 충족률", m.requirement_fulfillment_rate],
  ];
  $("metricsGrid").innerHTML = metricDefs
    .map(([label, val]) => {
      const display = val === null || val === undefined ? "—" : val;
      return `<div class="metric"><div class="label">${label}</div><div class="val">${display}</div></div>`;
    })
    .join("");
}

function filteredItems(items) {
  const st = $("filterStatus").value;
  const qa = $("filterQa").value;
  const reworkOnly = $("filterRework").checked;
  let list = [...items];
  if (st) list = list.filter((i) => i.status === st);
  if (qa) list = list.filter((i) => i.qa_status === qa);
  if (reworkOnly) list = list.filter((i) => i.qa_rework_count >= 1);
  const sort = $("sortBy").value;
  list.sort((a, b) => {
    if (sort === "rework") return b.qa_rework_count - a.qa_rework_count;
    if (sort === "progress") return b.progress - a.progress;
    return (b.last_updated_at || "").localeCompare(a.last_updated_at || "");
  });
  return list;
}

function renderTable(data) {
  const items = filteredItems(data.items || []);
  $("itemTable").innerHTML = items
    .map(
      (i) => `<tr class="${selectedId === i.req_id ? "active" : ""}" data-id="${i.req_id}">
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
      renderDetail(data);
      renderTable(data);
    });
  });

  const sel = $("cmdReqIds");
  const prev = new Set([...sel.selectedOptions].map((o) => o.value));
  sel.innerHTML = (data.items || [])
    .map(
      (i) =>
        `<option value="${i.req_id}" ${prev.has(i.req_id) ? "selected" : ""}>${i.req_id} — ${i.title}</option>`
    )
    .join("");
}

function renderDetail(data) {
  const item = (data.items || []).find((i) => i.req_id === selectedId);
  if (!item) {
    $("itemDetail").textContent = "항목을 선택하세요.";
    return;
  }
  $("itemDetail").innerHTML = `
    <div><span class="muted">ID</span> ${item.req_id}</div>
    <div><span class="muted">제목</span> ${item.title}</div>
    <div><span class="muted">priority</span> ${item.priority || "—"}</div>
    <div><span class="muted">spec_ref</span> ${item.spec_ref || "—"}</div>
    <div><span class="muted">acceptance</span> ${item.acceptance_criteria || "—"}</div>
    <div><span class="muted">target_files</span> ${item.target_files || "—"}</div>
    <div><span class="muted">dev_note</span> ${item.dev_note || "—"}</div>
    <div><span class="muted">qa_diff_note</span> ${item.qa_diff_note || "—"}</div>
    <div><span class="muted">갱신</span> ${item.last_updated_by} @ ${item.last_updated_at}</div>
  `;
}

function renderCommands(data) {
  $("cmdList").innerHTML =
    (data.commands || [])
      .map(
        (c) =>
          `<div>[${c.status}] ${c.command_type} → ${c.target} (${(c.req_ids || []).join(",")}) ${
            c.ack_latency_ms != null ? c.ack_latency_ms + "ms" : ""
          }</div>`
      )
      .join("") || `<div>명령 없음</div>`;
}

async function refresh() {
  try {
    const [stateRes, histRes] = await Promise.all([
      fetch("/api/state"),
      fetch("/api/history?limit=80"),
    ]);
    if (!stateRes.ok) throw new Error("API 응답 실패: " + stateRes.status);
    state = await stateRes.json();
    const hist = await histRes.json();

    const w = state.watch || {};
    $("lastSync").textContent = w.last_sync_at || "—";
    if (w.warning) {
      $("warning").textContent = w.warning;
      $("warning").classList.remove("hidden");
    } else {
      $("warning").classList.add("hidden");
    }

    renderDashboard(state);
    renderTable(state);
    renderDetail(state);
    renderCommands(state);

    $("logList").innerHTML = (hist.events || [])
      .slice()
      .reverse()
      .map(
        (e) =>
          `<div>${e.ts} · ${e.event_type} · ${JSON.stringify(e.payload).slice(0, 160)}</div>`
      )
      .join("");

    countdown = 5;
  } catch (err) {
    $("warning").textContent = "서버 연결 실패: " + err;
    $("warning").classList.remove("hidden");
  }
}

$("cmdForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const req_ids = [...$("cmdReqIds").selectedOptions].map((o) => o.value);
  if (!req_ids.length) {
    alert("항목을 하나 이상 선택하세요.");
    return;
  }
  const body = {
    target: fd.get("target"),
    req_ids,
    command_type: fd.get("command_type"),
    note: fd.get("note") || "",
  };
  const res = await fetch("/api/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.detail || "명령 실패");
    return;
  }
  await refresh();
});

["filterStatus", "filterQa", "filterRework", "sortBy"].forEach((id) => {
  $(id).addEventListener("change", () => state && renderTable(state));
});

setInterval(() => {
  countdown = Math.max(0, countdown - 1);
  $("countdown").textContent = String(countdown);
  tokenCountdown = Math.max(0, tokenCountdown - 1);
  const tc = $("tokenCountdown");
  if (tc) tc.textContent = String(tokenCountdown);
}, 1000);

$("tokenSetForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const usedPct = Number($("tokenUsedInput").value);
  if (Number.isNaN(usedPct) || usedPct < 0 || usedPct > 100) {
    alert("0~100 사이 숫자를 입력하세요.");
    return;
  }
  const res = await fetch("/api/tokens", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ used_pct: usedPct, source: "ui" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.detail || "사용량 반영 실패");
    return;
  }
  renderTokens(await res.json());
  tokenCountdown = 10;
});

refresh();
setInterval(refresh, POLL_MS);
refreshTokens();
setInterval(refreshTokens, TOKEN_POLL_MS);
