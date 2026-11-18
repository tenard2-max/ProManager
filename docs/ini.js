/** INI 파서 (interpolation 없음). UTF-8 BOM 허용. */

export function parseIni(text) {
  const raw = String(text || "").replace(/^\uFEFF/, "");
  const sections = {};
  let current = null;
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(";") || trimmed.startsWith("#")) continue;
    const sec = trimmed.match(/^\[(.+)]$/);
    if (sec) {
      current = sec[1].trim();
      sections[current] = sections[current] || {};
      continue;
    }
    if (!current) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    sections[current][key] = value;
  }
  return sections;
}

export function statusFromIni(sections) {
  const meta = sections.META || {};
  const items = [];
  const statusCounts = {
    TODO: 0,
    IN_PROGRESS: 0,
    IN_REVIEW: 0,
    REWORK_REQUESTED: 0,
    VERIFIED: 0,
  };
  const cursorCats = {};
  const grokCats = {};

  for (const [name, sec] of Object.entries(sections)) {
    if (name === "META" || !name.startsWith("REQ_")) continue;
    const progress = Number(sec.progress || 0);
    const qaScore = Number(sec.qa_score || 0);
    const item = {
      req_id: name,
      title: sec.title || "",
      category: sec.category || "",
      status: sec.status || "TODO",
      progress,
      qa_status: sec.qa_status || "PENDING",
      qa_score: qaScore,
      qa_rework_count: Number(sec.qa_rework_count || 0),
      dev_note: sec.dev_note || "",
      qa_diff_note: sec.qa_diff_note || "",
      last_updated_by: sec.last_updated_by || "",
      last_updated_at: sec.last_updated_at || "",
    };
    items.push(item);
    if (item.status in statusCounts) statusCounts[item.status] += 1;

    const cursorRaw = Math.min(Math.max(progress, 0), 60);
    const cursorPct = Math.round((100 * cursorRaw) / 60 * 100) / 100;
    (cursorCats[item.category] ||= []).push(cursorPct);

    let grokVal = 0;
    if (item.qa_status === "PASSED" || item.status === "VERIFIED") {
      grokVal = qaScore;
    } else if (progress >= 80) {
      grokVal = Math.max(0, Math.min(100, (progress - 80) / 0.2));
    }
    (grokCats[item.category] ||= []).push(Math.round(grokVal * 100) / 100);
  }

  const avg = (arr) =>
    arr.length ? Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 100) / 100 : 0;

  return {
    meta: {
      project_name: meta.project_name || "",
      total_tasks: Number(meta.total_tasks || items.length),
      overall_progress: Number(meta.overall_progress || avg(items.map((i) => i.progress))),
      state_version: Number(meta.state_version || 0),
      last_updated_by: meta.last_updated_by || "",
      last_updated_at: meta.last_updated_at || "",
    },
    items,
    status_counts: statusCounts,
    category_progress_cursor: Object.fromEntries(
      Object.entries(cursorCats).map(([k, v]) => [k, avg(v)])
    ),
    category_progress_grok: Object.fromEntries(
      Object.entries(grokCats).map(([k, v]) => [k, avg(v)])
    ),
  };
}

export function tokensFromJson(text) {
  try {
    const t = JSON.parse(text);
    const weekly = Math.max(1, Number(t.weekly_included || 1));
    const cursor = Math.max(0, Number(t.cursor_used || 0));
    const grok = Math.max(0, Number(t.grok_used || 0));
    const total = cursor + grok;
    return {
      plan: t.plan || "Premium",
      used_pct: Math.round((1000 * total) / weekly) / 10,
      cursor_pct: Math.round((1000 * cursor) / weekly) / 10,
      grok_pct: Math.round((1000 * grok) / weekly) / 10,
      renews_at: t.renews_at || "",
      source: t.source || "file",
    };
  } catch {
    return null;
  }
}
