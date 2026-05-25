/* interactive.js — 外送路由互動式規劃前端邏輯
 * 依賴：window.MAP_CONFIG 由 interactive_map.html 注入；Leaflet 已載入
 */

// ─── 全域狀態 ────────────────────────────────────────────────────────────────
let clickMode = "pickup";            // "pickup" | "dropoff" | "start"
let pickupMarkers  = [];             // { marker, lat, lng }
let dropoffMarkers = [];             // { marker, lat, lng }
let startMarker    = null;           // { marker, lat, lng } | null

let routePolylines  = {};            // {resultsIndex: L.Polyline}
let snappedMarkers  = [];            // L.CircleMarker[] (snapped 點)
let highlightedIdx  = -1;            // 目前高亮的演算法 index

let prepTimes       = [];            // 各訂單餐點製作時間（分鐘），index 對應取餐點順序

const ALGO_COLORS = ["#e67e22", "#2980b9", "#27ae60"];  // greedy, tsp, dp
const PREP_MIN = 0, PREP_MAX = 25;   // 製作時間範圍（分鐘）
const WAIT_TOLERANCE_S = 180;        // 騎手在餐廳的等待容忍門檻（秒）

// 新訂單的預設製作時間：5～20 分鐘隨機，讓示範更有變化
function randomPrep() {
  return Math.floor(5 + Math.random() * 16);
}

// ─── Leaflet 地圖初始化 ───────────────────────────────────────────────────────
const cfg = window.MAP_CONFIG;
const map = L.map("map").setView([cfg.centerLat, cfg.centerLng], cfg.zoom);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

// ─── 工具函式：建立彩色圖示 ───────────────────────────────────────────────────
function makeIcon(color, label) {
  return L.divIcon({
    className: "",
    html: `<div style="
      background:${color};
      border:2px solid rgba(0,0,0,0.35);
      border-radius:50%;
      width:22px; height:22px;
      display:flex; align-items:center; justify-content:center;
      color:#fff; font-size:10px; font-weight:bold;
      box-shadow:0 1px 4px rgba(0,0,0,0.4);
    ">${label}</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    popupAnchor: [0, -14],
  });
}

// ─── 更新已佈點計數 ───────────────────────────────────────────────────────────
function updateCounts() {
  document.getElementById("count-pickup").textContent = pickupMarkers.length;
  document.getElementById("count-dropoff").textContent = dropoffMarkers.length;
  renderPrepConfig();
}

// ─── 製作時間設定面板（依取餐點數量動態產生一列） ─────────────────────────────
function renderPrepConfig() {
  const list = document.getElementById("prep-list");
  if (!list) return;
  const n = pickupMarkers.length;

  if (n === 0) {
    prepTimes = [];
    list.innerHTML =
      '<p style="font-size:0.78rem;color:#aaa;">尚未新增取餐點。新增取餐點後即可設定其製作時間。</p>';
    return;
  }

  // 為新出現的訂單填預設值；超出的丟棄
  for (let i = 0; i < n; i++) {
    if (typeof prepTimes[i] !== "number") prepTimes[i] = randomPrep();
  }
  prepTimes.length = n;

  let html = "";
  for (let i = 0; i < n; i++) {
    const v = prepTimes[i];
    html += `
      <div class="prep-row">
        <span class="prep-dot"></span>
        <label>訂單 #${i + 1}</label>
        <input type="range" min="${PREP_MIN}" max="${PREP_MAX}" step="1" value="${v}"
               oninput="onPrepChange(${i}, this.value)" />
        <input type="number" min="${PREP_MIN}" max="${PREP_MAX}" step="1" value="${v}"
               id="prep-num-${i}" onchange="onPrepChange(${i}, this.value)" />
        <span class="prep-unit">分鐘</span>
      </div>`;
  }
  list.innerHTML = html;
}

// 製作時間變更：夾在 [0, 25]，同步同一列的 range 與 number 顯示
function onPrepChange(i, raw) {
  let v = Math.round(Number(raw));
  if (!Number.isFinite(v)) v = 0;
  v = Math.max(PREP_MIN, Math.min(PREP_MAX, v));
  prepTimes[i] = v;
  const row = document.querySelectorAll("#prep-list .prep-row")[i];
  if (row) {
    const range = row.querySelector('input[type="range"]');
    const num = row.querySelector('input[type="number"]');
    if (range) range.value = v;
    if (num) num.value = v;
  }
}

// ─── 模式切換 ────────────────────────────────────────────────────────────────
function setMode(mode) {
  clickMode = mode;
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("btn-" + mode).classList.add("active");
}

// ─── 地圖點擊 ────────────────────────────────────────────────────────────────
map.on("click", function (e) {
  const { lat, lng } = e.latlng;

  if (clickMode === "pickup") {
    const idx = pickupMarkers.length + 1;
    const m = L.marker([lat, lng], { icon: makeIcon("#e67e22", idx) })
      .bindPopup(`取餐點 #${idx}`)
      .addTo(map);
    pickupMarkers.push({ marker: m, lat, lng });
    updateCounts();
  } else if (clickMode === "dropoff") {
    const idx = dropoffMarkers.length + 1;
    const m = L.marker([lat, lng], { icon: makeIcon("#2980b9", idx) })
      .bindPopup(`送餐點 #${idx}`)
      .addTo(map);
    dropoffMarkers.push({ marker: m, lat, lng });
    updateCounts();
  } else if (clickMode === "start") {
    // 只允許一個司機起點
    if (startMarker) {
      map.removeLayer(startMarker.marker);
    }
    const m = L.marker([lat, lng], { icon: makeIcon("#2c3e50", "S") })
      .bindPopup("司機起點")
      .addTo(map);
    startMarker = { marker: m, lat, lng };
  }
});

// ─── 清除全部 ────────────────────────────────────────────────────────────────
function clearAll() {
  [...pickupMarkers, ...dropoffMarkers].forEach(o => map.removeLayer(o.marker));
  if (startMarker) map.removeLayer(startMarker.marker);
  pickupMarkers  = [];
  dropoffMarkers = [];
  startMarker    = null;
  prepTimes      = [];
  updateCounts();
  clearRoutes();
  document.getElementById("results-area").innerHTML =
    '<p style="color:#aaa; font-size:0.85rem; text-align:center; margin-top:20px;">請在地圖上點擊新增取餐點與送餐點，<br/>再按「⚡ 計算路線」。</p>';
  hideError();
}

// ─── 清除路線圖層 ─────────────────────────────────────────────────────────────
function clearRoutes() {
  Object.values(routePolylines).forEach(p => map.removeLayer(p));
  snappedMarkers.forEach(m => map.removeLayer(m));
  routePolylines = {};
  snappedMarkers = [];
  highlightedIdx = -1;
}

// ─── 錯誤橫幅 ────────────────────────────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById("error-banner");
  el.textContent = "⚠ " + msg;
  el.style.display = "block";
}
function hideError() {
  document.getElementById("error-banner").style.display = "none";
}

// ─── 計算路線（主邏輯） ──────────────────────────────────────────────────────
async function computeRoute() {
  hideError();

  if (pickupMarkers.length === 0 || dropoffMarkers.length === 0) {
    showError("請至少各新增一個取餐點與送餐點。");
    return;
  }

  const speedVal = parseFloat(document.getElementById("speed-input").value) || 5.0;

  const payload = {
    pickups:   pickupMarkers.map(o => [o.lat, o.lng]),
    dropoffs:  dropoffMarkers.map(o => [o.lat, o.lng]),
    start:     startMarker ? [startMarker.lat, startMarker.lng] : null,
    speed_mps: speedVal,
    // 每筆訂單的製作時間（分鐘），長度對應取餐點數量
    prep_times_min: pickupMarkers.map((_, i) =>
      typeof prepTimes[i] === "number" ? prepTimes[i] : 0),
  };

  // 顯示載入中
  document.getElementById("loading").classList.add("show");

  let data;
  try {
    const resp = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    data = await resp.json();
  } catch (err) {
    document.getElementById("loading").classList.remove("show");
    showError("網路錯誤：" + err.message);
    return;
  }

  document.getElementById("loading").classList.remove("show");

  if (!data.ok) {
    showError(data.error || "未知錯誤");
    return;
  }

  renderResults(data);
}

// 由 visited_stops 組出「停靠順序」字串，例如「取3 → 送3 → 取1 → ...」
function stopOrderStr(visited) {
  return (visited || [])
    .map(v => `${v.kind_zh}${v.order_id}`)
    .join(" → ");
}

// ─── 渲染結果 ────────────────────────────────────────────────────────────────
function renderResults(data) {
  clearRoutes();

  const { results, analysis } = data;

  // 繪製每個演算法的「單一連續路線」（沿有向道路、經過各 approach 馬路位置）
  const bounds = [];
  results.forEach((r, i) => {
    if (!r.success || !r.polyline || r.polyline.length === 0) return;
    const poly = L.polyline(r.polyline, {
      color: ALGO_COLORS[i],
      weight: 4,
      opacity: 0.85,
    }).addTo(map);
    routePolylines[i] = poly;
    r.polyline.forEach(pt => bounds.push(pt));
  });
  if (bounds.length > 0) {
    map.fitBounds(L.latLngBounds(bounds), { padding: [30, 30] });
  }

  // approach 馬路位置 + 接駁虛線（approach 三演算法相同，取第一個成功結果繪製一次）
  const base = results.find(r => r.success) || results[0];
  (base.visited_stops || []).forEach(vs => {
    const isPickup = vs.stop_type === "pickup";
    const color = isPickup ? "#e67e22" : "#2980b9";
    // approach：實際可合法抵達的馬路位置（小方點）
    const m = L.circleMarker(vs.approach_latlng, {
      radius: 5, color: "#fff", weight: 2, fillColor: color, fillOpacity: 1,
    }).bindTooltip(`${vs.kind_zh}#${vs.order_id}（可抵達馬路位置）`, { direction: "top" }).addTo(map);
    snappedMarkers.push(m);
    // 接駁虛線：馬路位置 → 門口原始點（最後幾公尺步行/牽車，非機車道路）
    const dash = L.polyline([vs.approach_latlng, vs.original_latlng], {
      color, weight: 2, opacity: 0.7, dashArray: "4 5",
    }).addTo(map);
    snappedMarkers.push(dash);
  });

  // ── 建立 HTML ────────────────────────────────────────────────────────────
  let html = `<h2>演算法比較</h2>`;

  const allVisited = results.every(r => r.all_stops_visited);
  html += `<p style="font-size:0.85rem;font-weight:bold;padding:6px 8px;border-radius:4px;margin-bottom:10px;`
        + (allVisited
            ? `background:#e8f8ef;color:#1e7e44;">✓ 所有取餐／送餐點皆已抵達（最近可合法停靠的馬路位置）`
            : `background:#fde8e8;color:#c0392b;">⚠ 有取餐／送餐點未能抵達，詳見下表「是否皆抵達」`)
        + `</p>`;

  // 各訂單製作時間摘要（三演算法相同，取 base.orders_info）
  if (base.orders_info && base.orders_info.length > 0) {
    const items = base.orders_info
      .map(o => `#${o.order_id}：${o.prep_time_min} 分`)
      .join("　");
    html += `<p style="font-size:0.78rem;color:#666;margin-bottom:10px;">`
          + `🍳 餐點製作時間 — ${escHtml(items)}</p>`;
  }

  // 路線圖例
  html += `<div id="route-legend"><h3>路線圖例</h3>`;
  results.forEach((r, i) => {
    if (!r.success) return;
    html += `
      <div class="route-legend-item" onclick="highlightRoute(${i})">
        <div class="route-swatch" style="background:${ALGO_COLORS[i]};"></div>
        <span>${r.display_name} — ${fmtDist(r.total_distance_m)}</span>
      </div>`;
  });
  html += `</div>`;

  // 演算法比較表格
  html += `
    <table id="algo-table">
      <thead>
        <tr>
          <th>演算法</th>
          <th>停靠順序</th>
          <th>主路線距離</th>
          <th>停靠接近距離</th>
          <th>總距離</th>
          <th>預估時間</th>
          <th>騎手等待</th>
          <th>計算時間</th>
          <th>是否皆抵達</th>
        </tr>
      </thead>
      <tbody>`;

  results.forEach((r, i) => {
    const dash = "—";
    const orderStr = r.success ? escHtml(stopOrderStr(r.visited_stops))
                               : `失敗：${escHtml(r.error || "")}`;
    const roadStr = r.success ? fmtDist(r.road_distance_m) : dash;
    const apprStr = r.success ? `${Math.round(r.approach_distance_m)} 公尺` : dash;
    const totalStr = r.success ? fmtDist(r.total_distance_m) : dash;
    const timeStr = r.success ? fmtTime(r.total_time_s) : dash;
    const waitStr = r.success
      ? (fmtTime(r.total_wait_s)
          + (r.exceeds_wait_tolerance
              ? ' <span title="有取餐點等待超過 3 分鐘" style="color:#c0392b;">⚠</span>'
              : ""))
      : dash;
    const compStr = r.compute_ms.toFixed(2) + " 毫秒";
    const reachStr = r.success
      ? (r.all_stops_visited ? "✓ 全部抵達" : "✗ 未全抵達")
      : "✗ 失敗";
    const colorDot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${ALGO_COLORS[i]};margin-right:5px;"></span>`;
    html += `
      <tr onclick="highlightRoute(${i})" id="algo-row-${i}">
        <td>${colorDot}${escHtml(r.display_name)}</td>
        <td style="font-size:0.74rem;">${orderStr}</td>
        <td>${roadStr}</td>
        <td>${apprStr}</td>
        <td>${totalStr}</td>
        <td>${timeStr}</td>
        <td>${waitStr}</td>
        <td>${compStr}</td>
        <td>${reachStr}</td>
      </tr>`;
  });

  html += `</tbody></table>`;

  // 標記說明
  html += `<p style="font-size:0.74rem;color:#888;margin-bottom:10px;">`
        + `說明：路線沿單行道方向行駛（不逆向），需折返時會繞經路口。`
        + `實心 marker＝你點選的門口位置；小圓點＝機車可合法停靠的馬路位置；`
        + `虛線＝靠邊停車後步行/牽車的最後幾公尺（計入「停靠接近距離」，不計入主路線）。</p>`;

  // 分析說明
  html += `
    <div id="analysis-section">
      <h3>分析說明</h3>
      <p id="analysis-text">${escHtml(analysis)}</p>
    </div>`;

  document.getElementById("results-area").innerHTML = html;
}

// ─── 路線高亮 ────────────────────────────────────────────────────────────────
function highlightRoute(idx) {
  // 重置所有路線樣式
  Object.values(routePolylines).forEach(p => {
    p.setStyle({ weight: 4, opacity: 0.85 });
    p.bringToBack();
  });

  // 高亮選取行
  document.querySelectorAll("#algo-table tbody tr").forEach(tr =>
    tr.classList.remove("row-active")
  );
  const row = document.getElementById(`algo-row-${idx}`);
  if (row) row.classList.add("row-active");

  // 若已是選取狀態則取消
  if (highlightedIdx === idx) {
    highlightedIdx = -1;
    return;
  }
  highlightedIdx = idx;

  // 高亮目標路線（查詢 map 而非陣列，保持 results index 對應）
  const p = routePolylines[idx];
  if (p) {
    p.setStyle({ weight: 7, opacity: 1.0 });
    p.bringToFront();
    map.fitBounds(p.getBounds(), { padding: [40, 40] });
  }
}

// ─── 格式化工具 ──────────────────────────────────────────────────────────────
function fmtDist(m) {
  const km = (m / 1000).toFixed(2);
  return `${Math.round(m)} 公尺（${km} 公里）`;
}

function fmtTime(s) {
  const mins = (s / 60).toFixed(1);
  return `${Math.round(s)} 秒（${mins} 分鐘）`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
