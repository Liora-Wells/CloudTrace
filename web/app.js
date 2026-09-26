/* CloudTrace Web 面板逻辑（与桌面版共享同一任务状态） */
"use strict";

/* ================= 基础 ================= */
let token = sessionStorage.getItem("ct_token") || "";
let state = {
  stage: "idle", busy: false, funnel: {}, progress: [0, 0, 0, 0],
  speed_progress: [0, 0, 0], scan_results: [], speed_results: [],
  log: [], last_error: null, version: "?", settings: {},
};
let scanResults = [];
let speedResults = [];
let selectedChips = new Set();
let settingsLoaded = false;
let es = null;
let lastDoneNote = "";

const DEFAULT_SETTINGS = {
  tray_on_close: false, cidr_mode: "仅官方", scan_mode: "tcping", sample_max: 5000,
  speed_url: "auto", min_speed: 0, verify_nodes: true,
  score_speed_weight: 3.0, score_latency_weight: 3.0,
  http_enabled: true, http_port: 17443, allow_lan: false, http_token: "",
};

const SCAN_FIELDS = {
  ip: "IP地址", iata_code: "地区码", chinese_name: "地区", latency: "延迟(ms)",
  ip_version: "IP版本", port: "端口", scan_mode: "扫描方式", scan_time: "扫描时间",
};
const SPEED_FIELDS = {
  ip: "IP地址", iata_code: "地区码", chinese_name: "地区", latency: "延迟(ms)",
  download_speed: "下载速度(MB/s)", score: "综合评分", verified: "可用性验证",
  port: "端口", test_type: "测速类型",
};

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (token) headers["X-Token"] = token;
  const resp = await fetch(path, Object.assign({}, opts, { headers }));
  if (resp.status === 401) {
    const t = prompt("请输入访问 Token:");
    if (t) {
      token = t.trim();
      sessionStorage.setItem("ct_token", token);
      connectSSE();
      return api(path, opts);
    }
    throw new Error("未授权");
  }
  if (!resp.ok) {
    let msg = "HTTP " + resp.status;
    try { const j = await resp.json(); if (j.error) msg = j.error; } catch (e) {}
    throw new Error(msg);
  }
  const ct = resp.headers.get("Content-Type") || "";
  if (ct.includes("json")) return resp.json();
  return resp;
}

function downloadURL(path) {
  const sep = path.includes("?") ? "&" : "?";
  const a = document.createElement("a");
  a.href = path + sep + "token=" + encodeURIComponent(token);
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* ================= 弹窗 ================= */
function showModal(title, bodyHTML, buttons) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = bodyHTML;
  const footer = document.getElementById("modal-footer");
  footer.innerHTML = "";
  (buttons || [{ label: "确定", cls: "btn-primary" }]).forEach(b => {
    const btn = document.createElement("button");
    btn.className = "btn " + (b.cls || "btn-ghost");
    btn.textContent = b.label;
    btn.onclick = () => {
      if (b.onClick && b.onClick() === false) return;
      hideModal();
    };
    footer.appendChild(btn);
  });
  document.getElementById("modal-backdrop").hidden = false;
}
function hideModal() { document.getElementById("modal-backdrop").hidden = true; }
function showInfo(msg) { showModal("提示", "<div>" + msg + "</div>", [{ label: "确定", cls: "btn-primary" }]); }
function showWarn(msg) { showModal("提示", "<div>" + msg + "</div>", [{ label: "确定", cls: "btn-primary" }]); }
function confirmDialog(title, msg, onYes) {
  showModal(title, "<div>" + msg + "</div>", [
    { label: "取消", cls: "btn-ghost" },
    { label: "确认", cls: "btn-red", onClick: onYes },
  ]);
}
document.getElementById("modal-backdrop").addEventListener("click", e => {
  if (e.target.id === "modal-backdrop") hideModal();
});

/* ================= 页面导航 ================= */
const PAGES = ["scan", "result", "speed", "history", "settings"];
const TITLES = { scan: "扫描", result: "扫描结果", speed: "测速结果", history: "历史记录", settings: "设置" };
let currentPage = "scan";

function setPage(name) {
  currentPage = name;
  PAGES.forEach(p => {
    document.getElementById("page-" + p).classList.toggle("show", p === name);
  });
  document.querySelectorAll(".nav-item").forEach(el =>
    el.classList.toggle("active", el.dataset.page === name));
  document.getElementById("page-title").textContent = TITLES[name];
  renderCTA();
  if (name === "history") loadHistory();
}
document.querySelectorAll(".nav-item").forEach(el => {
  el.addEventListener("click", () => setPage(el.dataset.page));
});

const CTA_ACTIONS = {
  scan: () => startScan(),
  result: () => {
    if (selectedChips.size > 0) startSpeed("region");
    else startSpeed("all");
  },
  speed: () => openExport("speed"),
  history: () => setPage("scan"),
  settings: () => saveSettings(),
};
function renderCTA() {
  const btn = document.getElementById("btn-cta");
  const map = {
    scan: ["▶ 开始扫描", "btn-primary"], result: ["🚀 批量测速", "btn-orange"],
    speed: ["⬇ 导出结果", "btn-green"], history: ["🔄 前往扫描", "btn-primary"],
    settings: ["💾 保存设置", "btn-primary"],
  };
  const [label, cls] = map[currentPage];
  btn.textContent = label;
  btn.className = "btn " + cls;
}
document.getElementById("btn-cta").addEventListener("click", () => CTA_ACTIONS[currentPage]());

/* ================= 状态渲染 ================= */
function busy() { return state.stage !== "idle"; }

function renderStatus() {
  const pill = document.getElementById("status-pill");
  const stopBtn = document.getElementById("btn-stop");
  const cta = document.getElementById("btn-cta");
  let text = "就绪", cls = "";
  if (state.stage === "scanning") {
    const [c, t] = state.progress;
    text = t ? `扫描 ${c}/${t}` : "扫描中…"; cls = "run";
  } else if (state.stage === "testing") {
    const [c, t] = state.speed_progress;
    text = t ? `测速 ${c}/${t}` : "测速中…"; cls = "busy";
  } else if (lastDoneNote) {
    text = lastDoneNote; cls = "run";
  }
  if (state.last_error && state.stage === "idle") { text = "错误"; cls = "error"; }
  pill.textContent = text;
  pill.className = "pill " + cls;
  stopBtn.disabled = !busy();
  cta.disabled = busy();

  const p = state.stage === "testing" ? state.speed_progress : state.progress;
  const pct = p[1] ? Math.round(p[0] / p[1] * 100) : (state.stage === "idle" ? 0 : 0);
  document.getElementById("progress-bar").style.width = (busy() ? pct : (lastDoneNote ? 100 : 0)) + "%";

  const sp = state.speed_progress;
  document.getElementById("speed-label").textContent =
    state.stage === "scanning"
      ? `速度: ${state.progress[3] ? state.progress[3].toFixed(0) : 0} IP/s | 成功: ${state.progress[2]}`
      : `结果: 扫描 ${scanResults.length} · 测速 ${speedResults.length}`;
}

function appendLog(msg) {
  const stamp = new Date().toTimeString().slice(0, 8);
  ["scan-log", "speed-log"].forEach(id => {
    const el = document.getElementById(id);
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    el.textContent += `[${stamp}] ${msg}\n`;
    const lines = el.textContent.split("\n");
    if (lines.length > 2000) el.textContent = lines.slice(-2000).join("\n");
    if (atBottom) el.scrollTop = el.scrollHeight;
  });
}

function renderFunnel(el, steps) {
  el.innerHTML = steps.map((s, i) =>
    (i ? '<span class="arr">→</span>' : "") +
    `<span class="step">${s[0]} <b>${s[1]}</b></span>`).join("") ||
    '<span class="step">等待开始</span>';
}

function funnelSteps(funnel) {
  const steps = [];
  if (funnel && funnel.generated) {
    steps.push(["生成", funnel.generated]);
    steps.push(["延迟达标", funnel.latency_ok || 0]);
    steps.push(["地区解析", funnel.with_iata || 0]);
  }
  steps.push(["可用", scanResults.length]);
  return steps;
}

/* ================= SSE ================= */
function connectSSE() {
  if (es) { es.close(); es = null; }
  es = new EventSource("/api/events?token=" + encodeURIComponent(token));
  es.addEventListener("state", e => applyState(JSON.parse(e.data)));
  es.addEventListener("log", e => appendLog(JSON.parse(e.data)));
  es.addEventListener("progress", e => {
    state.progress = JSON.parse(e.data); renderStatus();
    renderFunnel(document.getElementById("scan-funnel"), funnelSteps(state.funnel));
  });
  es.addEventListener("funnel", e => {
    state.funnel = JSON.parse(e.data);
    renderFunnel(document.getElementById("scan-funnel"), funnelSteps(state.funnel));
  });
  es.addEventListener("speed_progress", e => { state.speed_progress = JSON.parse(e.data); renderStatus(); });
  es.addEventListener("scan_done", e => {
    const results = JSON.parse(e.data);
    state.stage = "idle";
    if (results) {
      scanResults = results;
      lastDoneNote = `完成 · ${results.length} IP`;
      renderResult();
      setPage("result");
      appendLog(`✅ 扫描完成: ${results.length} 个可用IP，已存入历史`);
    } else {
      lastDoneNote = "";
      appendLog("扫描已中止");
    }
    renderStatus();
  });
  es.addEventListener("speed_done", e => {
    const results = JSON.parse(e.data);
    state.stage = "idle";
    speedResults = results || [];
    if (speedResults.length) {
      const best = speedResults[0];
      lastDoneNote = `完成 · 最快 ${best.download_speed} MB/s`;
      appendLog(`✅ 测速完成: ${speedResults.length} 条结果，最优 ${best.ip} (${best.download_speed} MB/s, 评分 ${best.score})`);
    } else {
      lastDoneNote = "测速完成（无结果）";
    }
    renderSpeed();
    setPage("speed");
    renderStatus();
  });
  es.onerror = () => { /* EventSource 自动重连 */ };
}

function applyState(s) {
  const first = !settingsLoaded;
  Object.assign(state, s);
  document.getElementById("app-version").textContent = "v" + (s.version || "?");
  scanResults = s.scan_results || [];
  speedResults = s.speed_results || [];
  // 芯片选择保留交集
  const codes = new Set(scanResults.map(r => (r.iata_code || "").toUpperCase()).filter(c => c && c !== "UNKNOWN"));
  selectedChips = new Set([...selectedChips].filter(c => codes.has(c)));
  renderResult();
  renderSpeed();
  renderStatus();
  renderFunnel(document.getElementById("scan-funnel"), funnelSteps(state.funnel));
  if (first && s.settings) {
    populateSettings(Object.assign({}, DEFAULT_SETTINGS, s.settings));
    // 扫描页参数回填
    const st = s.settings;
    if (st.scan_mode) setSeg(document.getElementById("seg-mode"), st.scan_mode);
    if (st.sample_max) document.getElementById("in-sample").value = st.sample_max;
    if (st.cidr_mode && [...document.getElementById("sel-source").options].some(o => o.value === st.cidr_mode)) {
      document.getElementById("sel-source").value = st.cidr_mode;
    }
    onSourceChange();
    settingsLoaded = true;
  }
  if (s.stage === "idle") {
    if (s.scan_results && s.scan_results.length && !lastDoneNote) lastDoneNote = "";
  }
}

/* ================= 扫描 ================= */
function bindSeg(el, cb) {
  el.querySelectorAll("span").forEach(s => {
    s.addEventListener("click", () => {
      el.querySelectorAll("span").forEach(x => x.classList.remove("on"));
      s.classList.add("on");
      if (cb) cb(s.dataset.v);
    });
  });
}
function segVal(el) { return el.querySelector("span.on").dataset.v; }
function setSeg(el, v) {
  el.querySelectorAll("span").forEach(x => x.classList.toggle("on", x.dataset.v === String(v)));
}

function onSourceChange() {
  const mode = document.getElementById("sel-source").value;
  const isImport = mode === "非标列表";
  const isCustom = mode === "仅自定义" || mode === "官方+自定义";
  document.getElementById("wrap-cidr").hidden = !(isCustom && !isImport);
  document.getElementById("wrap-import").hidden = !isImport;
}
document.getElementById("sel-source").addEventListener("change", onSourceChange);

document.getElementById("file-import").addEventListener("change", e => {
  const f = e.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => { document.getElementById("txt-import").value = reader.result; };
  reader.readAsText(f, "utf-8");
});

async function startScan() {
  if (busy()) { showWarn("已有任务正在运行"); return; }
  const source = document.getElementById("sel-source").value;
  const body = {
    ip_version: parseInt(segVal(document.getElementById("seg-version")), 10),
    source_mode: source,
    port: parseInt(document.getElementById("in-port").value, 10),
    workers: parseInt(document.getElementById("in-workers").value, 10),
    threshold: parseInt(document.getElementById("in-threshold").value, 10),
    sample_max: parseInt(document.getElementById("in-sample").value, 10),
    ping_times: parseInt(document.getElementById("in-ping").value, 10),
    scan_mode: segVal(document.getElementById("seg-mode")),
  };
  if (source === "非标列表") {
    const text = document.getElementById("txt-import").value.trim();
    if (!text) { showWarn("非标列表不能为空（每行一个 IP [端口]）"); return; }
    body.import_text = text;
  } else if (source !== "仅官方") {
    const text = document.getElementById("txt-cidr").value.trim();
    if (!text) { showWarn("自定义 CIDR 不能为空"); return; }
    body.cidrs = text.split("\n").map(s => s.trim()).filter(Boolean);
  }
  try {
    await api("/api/scan/start", { method: "POST", body: JSON.stringify(body) });
    scanResults = [];
    selectedChips = new Set();
    state.funnel = {};
    state.progress = [0, 0, 0, 0];
    lastDoneNote = "";
    document.getElementById("scan-log").textContent = "";
    document.getElementById("speed-log").textContent = "";
    renderFunnel(document.getElementById("scan-funnel"), []);
    document.getElementById("meta-label").textContent =
      `IPv${body.ip_version} · 端口 ${body.port} · 并发 ${body.workers} · ${body.scan_mode === "httping" ? "HTTPing" : "TCPing"}`;
    state.stage = "scanning";
    renderStatus();
    renderResult();
  } catch (err) { showWarn("启动失败: " + err.message); }
}
document.getElementById("btn-start-scan").addEventListener("click", startScan);

/* ================= 结果页 ================= */
function latencyFactor() {
  const r = scanResults[0];
  if (!r) return 1;
  if ((r.scan_mode || "tcping") !== "httping") return 1;
  const tls = [443, 2053, 2083, 2087, 2096, 8443].includes(parseInt(r.port, 10));
  return tls ? 4.0 : 1.3;
}

function visibleScanResults() {
  let data = scanResults.slice();
  if (selectedChips.size) data = data.filter(r => selectedChips.has((r.iata_code || "").toUpperCase()));
  if (document.getElementById("chk-latency").checked) {
    const limit = parseFloat(document.getElementById("in-latency").value) * latencyFactor();
    data = data.filter(r => (r.latency || 0) < limit);
  }
  if (document.getElementById("sel-sort").value === "region") {
    data.sort((a, b) => ((a.iata_code || "zzz").localeCompare(b.iata_code || "zzz")) || (a.latency - b.latency));
  } else {
    data.sort((a, b) => (a.latency || 0) - (b.latency || 0));
  }
  return data;
}

function renderResult() {
  // 漏斗 + 摘要
  renderFunnel(document.getElementById("result-funnel"), funnelSteps(state.funnel));
  const mode = scanResults[0] && scanResults[0].scan_mode === "httping" ? "HTTPing" : "TCPing";
  document.getElementById("result-summary").textContent =
    scanResults.length ? `显示 ${visibleScanResults().length} / ${scanResults.length} 个 IP · 模式 ${mode}` : "暂无数据，请先扫描或加载历史";

  // 芯片
  const stat = {};
  scanResults.forEach(r => {
    const code = (r.iata_code || "").toUpperCase();
    if (!code || code === "UNKNOWN") return;
    if (!stat[code]) stat[code] = { count: 0, name: r.chinese_name || code };
    stat[code].count++;
  });
  const chipsEl = document.getElementById("region-chips");
  const entries = Object.entries(stat).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) {
    chipsEl.innerHTML = '<span class="hint">暂无地区数据</span>';
  } else {
    chipsEl.innerHTML = entries.map(([code, s]) =>
      `<button class="chip${selectedChips.has(code) ? " on" : ""}" data-code="${code}">${s.name} ${code} · <b>${s.count}</b></button>`
    ).join("");
    chipsEl.querySelectorAll(".chip").forEach(el => {
      el.addEventListener("click", () => {
        const code = el.dataset.code;
        if (selectedChips.has(code)) selectedChips.delete(code);
        else selectedChips.add(code);
        renderResult();
      });
    });
  }

  // 表格
  const factor = latencyFactor();
  const rows = visibleScanResults();
  const tbody = document.getElementById("scan-tbody");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">没有符合条件的结果</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const cls = r.latency < 100 * factor ? "lat-g" : (r.latency < 200 * factor ? "lat-o" : "lat-r");
    const region = r.iata_code ? `${r.chinese_name} (${r.iata_code})` : "未知";
    return `<tr>
      <td class="t-c"><input type="checkbox" data-ip="${r.ip}"></td>
      <td class="mono">${r.ip}</td>
      <td class="t-c">${region}</td>
      <td class="t-c ${cls}">${Number(r.latency).toFixed(1)} ms</td>
      <td class="t-c">${r.port || ""}</td>
      <td class="t-c">${r.scan_time || ""}</td>
    </tr>`;
  }).join("");
}

["chk-latency", "in-latency", "sel-sort"].forEach(id => {
  document.getElementById(id).addEventListener("change", renderResult);
});
document.getElementById("in-latency").addEventListener("input", renderResult);

document.getElementById("btn-single").addEventListener("click", () => {
  const checked = [...document.querySelectorAll("#scan-tbody input:checked")].map(c => c.dataset.ip);
  if (!checked.length) { showWarn("请先勾选要测速的 IP"); return; }
  startSpeed("selected", { ips: checked });
});
document.getElementById("btn-region-speed").addEventListener("click", () => {
  if (!selectedChips.size) { showWarn("请先点选地区芯片（可多选）"); return; }
  startSpeed("region", { codes: [...selectedChips] });
});
document.getElementById("btn-full-speed").addEventListener("click", () => startSpeed("all"));
document.getElementById("btn-export-scan").addEventListener("click", () => openExport("scan"));

/* ================= 测速 ================= */
async function startSpeed(scope, extra = {}) {
  if (busy()) { showWarn("已有任务正在运行"); return; }
  if (!scanResults.length) { showWarn("请先扫描或加载扫描结果"); return; }
  const body = Object.assign({ scope, count: parseInt(document.getElementById("in-count").value, 10) }, extra);
  if (document.getElementById("sel-speed-url").value === "manual") {
    body.speed_url = document.getElementById("in-speed-url").value.trim() || "auto";
  }
  if (document.getElementById("chk-minspeed").checked) {
    body.min_speed = parseFloat(document.getElementById("in-minspeed").value) || 0;
  }
  try {
    await api("/api/speed/start", { method: "POST", body: JSON.stringify(body) });
    speedResults = [];
    state.speed_progress = [0, 0, 0];
    lastDoneNote = "";
    document.getElementById("speed-log").textContent = "";
    state.stage = "testing";
    renderStatus();
    renderSpeed();
    setPage("speed");
  } catch (err) { showWarn("启动失败: " + err.message); }
}

document.getElementById("btn-region2").addEventListener("click", () => {
  const region = document.getElementById("in-region").value.trim().toUpperCase();
  if (!region) { showWarn("请输入地区码（如 HKG, NRT, SIN）"); return; }
  startSpeed("region", { codes: [region] });
});
document.getElementById("btn-full2").addEventListener("click", () => startSpeed("all"));
document.getElementById("btn-export-speed").addEventListener("click", () => openExport("speed"));

document.getElementById("sel-speed-url").addEventListener("change", e => {
  document.getElementById("in-speed-url").hidden = e.target.value !== "manual";
});
document.getElementById("in-region").addEventListener("input", e => {
  e.target.value = e.target.value.toUpperCase();
});

function visibleSpeedResults() {
  let data = speedResults;
  if (document.getElementById("chk-minspeed").checked) {
    const limit = parseFloat(document.getElementById("in-minspeed").value) || 0;
    data = data.filter(r => (r.download_speed || 0) >= limit);
  }
  return data;
}
["chk-minspeed", "in-minspeed"].forEach(id => {
  document.getElementById(id).addEventListener("change", renderSpeed);
});

function renderSpeed() {
  const rows = visibleSpeedResults();
  const tbody = document.getElementById("speed-tbody");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">暂无数据</td></tr>';
    return;
  }
  const rankCls = ["rank1", "rank2", "rank3"];
  tbody.innerHTML = rows.map((r, i) => {
    const latCls = r.latency < 100 ? "lat-g" : (r.latency < 200 ? "lat-o" : "lat-r");
    const spdCls = r.download_speed >= 10 ? "lat-g" : (r.download_speed >= 5 ? "lat-o" : "lat-r");
    const verify = r.verified === true ? "✓ " : (r.verified === false ? "✗ " : "");
    const vStyle = r.verified === false ? ' style="color:#EF4444"' : "";
    return `<tr>
      <td class="t-c ${rankCls[i] || ""}">${i + 1}</td>
      <td class="mono">${r.ip}</td>
      <td class="t-c"${vStyle}>${verify}${r.chinese_name || "未知"}(${r.iata_code || ""})</td>
      <td class="t-c ${latCls}">${Number(r.latency).toFixed(1)} ms</td>
      <td class="t-c ${spdCls}">${Number(r.download_speed).toFixed(2)} MB/s</td>
      <td class="t-c ${rankCls[i] ? "" : ""}"><b>${Number(r.score || 0).toFixed(1)}</b></td>
      <td class="t-c">${r.port || ""}</td>
      <td class="t-c"><span class="tag">${r.test_type || ""}</span></td>
    </tr>`;
  }).join("");
}

/* ================= 停止 ================= */
document.getElementById("btn-stop").addEventListener("click", () => {
  confirmDialog("确认停止", "确定要停止当前正在运行的任务吗？<br>未完成的进度将会丢失。", async () => {
    try {
      await api("/api/stop", { method: "POST", body: "{}" });
      appendLog("⚠️ 已请求停止任务");
    } catch (err) { showWarn("停止失败: " + err.message); }
  });
});

/* ================= 历史 ================= */
let histVersion = 4;
async function loadHistory() {
  const scanList = document.getElementById("hist-scan-list");
  const speedList = document.getElementById("hist-speed-list");
  scanList.innerHTML = speedList.innerHTML = '<div class="empty">加载中…</div>';
  for (const [type, el] of [["scan", scanList], ["speed", speedList]]) {
    try {
      const resp = await api(`/api/history?type=${type}&ipver=${histVersion}`);
      if (!resp.history.length) {
        el.innerHTML = `<div class="hint">暂无${type === "scan" ? "扫描" : "测速"}记录</div>`;
        continue;
      }
      el.innerHTML = resp.history.map(h => `
        <div class="hist">
          <span>${type === "scan" ? "📡" : "🚀"}</span>
          <div><div class="t">${h.save_time}</div>
          <div class="m">${h.count} 个 IP · ${h.filename}</div></div>
          <div class="ops">
            <button class="btn btn-primary btn-sm" data-act="load">加载</button>
            <button class="btn btn-ghost btn-sm" data-act="export">导出</button>
            <button class="btn btn-red btn-sm" data-act="del">删除</button>
          </div>
        </div>`).join("");
      el.querySelectorAll(".hist").forEach((rowEl, idx) => {
        const h = resp.history[idx];
        rowEl.querySelector('[data-act="load"]').onclick = () => loadHistoryFile(h.filepath, type);
        rowEl.querySelector('[data-act="export"]').onclick = () =>
          downloadURL(`/api/history/export?filepath=${encodeURIComponent(h.filepath)}&type=${type}&format=csv`);
        rowEl.querySelector('[data-act="del"]').onclick = () =>
          confirmDialog("确认删除", "确定要删除这条历史记录吗？<br>该操作不可恢复。", async () => {
            try {
              await api("/api/history", { method: "DELETE", body: JSON.stringify({ filepath: h.filepath }) });
              loadHistory();
            } catch (err) { showWarn("删除失败: " + err.message); }
          });
      });
    } catch (err) {
      el.innerHTML = `<div class="hint">加载失败: ${err.message}</div>`;
    }
  }
}
async function loadHistoryFile(filepath, type) {
  try {
    const resp = await api("/api/history/load", {
      method: "POST", body: JSON.stringify({ filepath, type }),
    });
    if (type === "scan") {
      scanResults = resp.results;
      selectedChips = new Set();
      state.funnel = {};
      renderResult();
      appendLog(`✅ 已加载扫描记录 (${resp.save_time})，共 ${resp.results.length} 个IP`);
      lastDoneNote = `已加载 ${resp.results.length} IP`;
      setPage("result");
    } else {
      speedResults = resp.results;
      renderSpeed();
      appendLog(`✅ 已加载测速记录 (${resp.save_time})，共 ${resp.results.length} 条`);
      setPage("speed");
    }
    renderStatus();
  } catch (err) { showWarn("加载失败: " + err.message); }
}
bindSeg(document.getElementById("seg-hist-ver"), v => { histVersion = parseInt(v, 10); loadHistory(); });
document.getElementById("btn-hist-refresh").addEventListener("click", loadHistory);

/* ================= 导出弹窗 ================= */
function openExport(type) {
  const hasScan = type === "scan" || (type === "both" && scanResults.length);
  const hasSpeed = type === "speed" || (type === "both" && speedResults.length);
  if (!scanResults.length && !speedResults.length) { showWarn("没有可导出的结果"); return; }

  const merged = Object.assign({}, SCAN_FIELDS, SPEED_FIELDS);
  const fieldsHTML = Object.entries(merged).map(([k, label]) =>
    `<label class="check"${k === "ip" ? ' style="opacity:.6"' : ""}>
      <input type="checkbox" class="ex-field" value="${k}" checked${k === "ip" ? " disabled" : ""}> ${label}
    </label>`).join("");

  const body = `
    <div class="sec"><div class="sec-title">格式</div>
      <div class="row"><label class="check"><input type="radio" name="exfmt" value="csv" checked> CSV</label>
      <label class="check"><input type="radio" name="exfmt" value="json"> JSON</label></div></div>
    <div class="sec"><div class="sec-title">导出字段</div><div class="fields">${fieldsHTML}</div></div>
    ${hasSpeed ? `<div class="sec"><div class="sec-title">筛选</div>
      <label class="check"><input type="checkbox" id="ex-qualified"> 仅导出合格结果，低于
      <input type="number" id="ex-minspeed" value="5" min="0" step="0.5" style="width:70px"> MB/s</label></div>` : ""}
  `;
  showModal(`导出${type === "scan" ? "扫描" : "测速"}结果`, body, [
    { label: "取消", cls: "btn-ghost" },
    {
      label: "导出", cls: "btn-primary", onClick: () => {
        const fmt = document.querySelector('input[name="exfmt"]:checked').value;
        const fields = [...document.querySelectorAll(".ex-field:checked")].map(c => c.value);
        const target = hasSpeed && (!hasScan || type !== "scan") ? "speed" : "scan";
        let url = `/api/export?type=${target}&format=${fmt}`;
        if (fields.length && fields.length < Object.keys(merged).length) url += "&fields=" + fields.join(",");
        const q = document.getElementById("ex-qualified");
        if (target === "speed" && q && q.checked) {
          url += "&qualified_only=1&min_speed=" + (parseFloat(document.getElementById("ex-minspeed").value) || 0);
        }
        downloadURL(url);
      },
    },
  ]);
}

/* ================= 设置 ================= */
function bindSwitch(id) {
  const el = document.getElementById(id);
  el.addEventListener("click", () => el.classList.toggle("on"));
  return el;
}
function setSwitch(id, on) { document.getElementById(id).classList.toggle("on", !!on); }
["sw-tray", "sw-verify", "sw-http", "sw-lan"].forEach(bindSwitch);

function populateSettings(s) {
  setSwitch("sw-tray", s.tray_on_close);
  document.getElementById("set-scan-mode").value = s.scan_mode;
  document.getElementById("set-sample").value = s.sample_max;
  const manual = s.speed_url && s.speed_url !== "auto";
  document.getElementById("set-speed-url-mode").value = manual ? "manual" : "auto";
  document.getElementById("row-speed-url").hidden = !manual;
  document.getElementById("set-speed-url").value = manual ? s.speed_url : "";
  setSwitch("sw-verify", s.verify_nodes);
  document.getElementById("set-minspeed").value = s.min_speed;
  document.getElementById("set-interval").value = s.download_interval != null ? s.download_interval : 3;
  document.getElementById("set-w-speed").value = s.score_speed_weight;
  document.getElementById("set-w-latency").value = s.score_latency_weight;
  setSwitch("sw-http", s.http_enabled);
  document.getElementById("set-port").value = s.http_port;
  setSwitch("sw-lan", s.allow_lan);
  document.getElementById("set-token").value = s.http_token || "";
  updateHttpHint();
}
document.getElementById("set-speed-url-mode").addEventListener("change", e => {
  document.getElementById("row-speed-url").hidden = e.target.value !== "manual";
});
["sw-http", "sw-lan"].forEach(id =>
  document.getElementById(id).addEventListener("click", updateHttpHint));

function updateHttpHint() {
  const on = document.getElementById("sw-http").classList.contains("on");
  const port = document.getElementById("set-port").value;
  const lan = document.getElementById("sw-lan").classList.contains("on");
  document.getElementById("http-hint").textContent = on
    ? `面板地址: ${lan ? "http://<本机IP>" : location.origin.replace(/:\d+$/, ":" + port)}  ·  HTTP 相关设置重启服务后生效`
    : "HTTP 服务已关闭（重启后不再启动）";
}

function collectSettings() {
  const manual = document.getElementById("set-speed-url-mode").value === "manual";
  return {
    tray_on_close: document.getElementById("sw-tray").classList.contains("on"),
    scan_mode: document.getElementById("set-scan-mode").value,
    sample_max: parseInt(document.getElementById("set-sample").value, 10) || 5000,
    speed_url: manual ? (document.getElementById("set-speed-url").value.trim() || "auto") : "auto",
    verify_nodes: document.getElementById("sw-verify").classList.contains("on"),
    min_speed: parseFloat(document.getElementById("set-minspeed").value) || 0,
    download_interval: parseInt(document.getElementById("set-interval").value, 10),
    score_speed_weight: parseFloat(document.getElementById("set-w-speed").value) || 0,
    score_latency_weight: parseFloat(document.getElementById("set-w-latency").value) || 0,
    http_enabled: document.getElementById("sw-http").classList.contains("on"),
    http_port: parseInt(document.getElementById("set-port").value, 10) || 17443,
    allow_lan: document.getElementById("sw-lan").classList.contains("on"),
    http_token: document.getElementById("set-token").value.trim(),
  };
}

async function saveSettings() {
  try {
    const resp = await api("/api/settings", { method: "PUT", body: JSON.stringify(collectSettings()) });
    populateSettings(Object.assign({}, DEFAULT_SETTINGS, resp.settings));
    const health = await api("/api/health");
    if (health.warnings.length) {
      showModal("设置已保存", "<div>设置已保存</div><div class='sec-title' style='margin-top:10px'>⚠ 体检提醒</div>" +
        "<ul class='warn-list'>" + health.warnings.map(w => `<li>${w}</li>`).join("") + "</ul>",
        [{ label: "确定", cls: "btn-primary" }]);
    } else {
      showInfo("设置已保存 ✓");
    }
  } catch (err) { showWarn("保存失败: " + err.message); }
}
async function restoreSettings() {
  confirmDialog("恢复默认", "确定恢复全部默认设置吗？", async () => {
    try {
      const resp = await api("/api/settings", { method: "PUT", body: JSON.stringify(DEFAULT_SETTINGS) });
      populateSettings(Object.assign({}, DEFAULT_SETTINGS, resp.settings));
      showInfo("已恢复默认设置");
    } catch (err) { showWarn("操作失败: " + err.message); }
  });
}
async function healthCheck() {
  try {
    const health = await api("/api/health");
    if (health.warnings.length) {
      showModal("配置体检", "<div>发现以下可优化项:</div><ul class='warn-list'>" +
        health.warnings.map(w => `<li>${w}</li>`).join("") + "</ul>",
        [{ label: "确定", cls: "btn-primary" }]);
    } else {
      showInfo("未发现配置问题 ✓");
    }
  } catch (err) { showWarn("体检失败: " + err.message); }
}
document.getElementById("btn-set-save").addEventListener("click", saveSettings);
document.getElementById("btn-set-restore").addEventListener("click", restoreSettings);
document.getElementById("btn-set-health").addEventListener("click", healthCheck);

/* ================= 启动 ================= */
async function boot() {
  bindSeg(document.getElementById("seg-version"));
  bindSeg(document.getElementById("seg-mode"));
  try {
    const s = await api("/api/state");
    applyState(s);
  } catch (err) {
    showWarn("无法获取状态: " + err.message);
  }
  connectSSE();
  renderCTA();
  renderStatus();
  onSourceChange();
}
boot();
