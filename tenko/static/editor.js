"use strict";
const DAYS = ["ED", "MO", "TU", "WE", "TH", "FR", "SA", "SU"];
const NAMES = {ED: "Every day", MO: "Monday", TU: "Tuesday", WE: "Wednesday", TH: "Thursday", FR: "Friday", SA: "Saturday", SU: "Sunday"};
const $ = id => document.getElementById(id);
let record = null, serial = "", draft = {}, draftRevision = 0, saveQueue = Promise.resolve();
let draftFailed = false;
const clone = value => JSON.parse(JSON.stringify(value));
const controls = [
  ["USE", null, "Control mode", ["Temp", "GraphD", "GraphW"]],
  ["TMP", 0, "Constant enabled", ["On", "Off"]], ["TMP", 1, "Stored air target (C)", [7, 40, .1]],
  ["FI", 0, "Flow cutoff (C)", [10, 75, 1]], ["FI", 1, "Flow restart drop (C)", [1, 9, 1]],
  ["RE", 0, "Return cutoff (C)", [10, 75, 1]], ["RE", 1, "Return restart drop (C)", [1, 9, 1]],
  ["PMT", 0, "PMT enabled", ["On", "Off"]], ["PMT", 1, "PMT restart (C)", [6, 15, 1]],
  ["PMT", 2, "PMT stop (C)", [7, 17, 1]], ["pNA", 0, "Pump lead-in (min)", [1, 15, 1]],
  ["pNA", 1, "Pump run-on (min)", [1, 15, 1]], ["MOD", null, "Automatic modulation", ["On", "Off"]],
  ["STU", 0, "Manual stage 1", ["On", "Off"]], ["STU", 1, "Manual stage 2", ["On", "Off"]],
];
function option(value, text) {
  const node = document.createElement("option"); node.value = value; node.textContent = text; return node;
}
function notify(text, error = false) { $("message").textContent = text; $("message").className = error ? "error" : "ok"; }
async function api(path, method = "GET", data = null) {
  const response = await fetch(path, {method, headers: method === "GET" ? {} :
    {"Content-Type": "application/json", "X-Tenko-Request": "1"}, body: data === null ? null : JSON.stringify(data)});
  if (!response.ok) {
    const body = await response.json(); throw new Error(body.error || `HTTP ${response.status}`);
  }
  return response.json();
}
const endpoint = () => `/api/boilers/${encodeURIComponent(serial)}`;
const reported = () => record?.report?.settings || {};
const day = () => $("day").value;
function pointsFor(key, layer = $("layer").value) {
  if (layer === "reported") return reported()[key];
  if (layer === "pending") return record?.pending[key];
  return draft[key] || reported()[key];
}
function saveDraft() {
  const snapshot = clone(draft), target = endpoint();
  $("draft-status").textContent = "Saving draft...";
  saveQueue = saveQueue.catch(() => {}).then(async () => {
    if (draftFailed) throw new Error("Draft saving is blocked; reload to resolve the conflict");
    try {
      const saved = await api(`${target}/draft`, "PUT", {draft: snapshot, revision: draftRevision});
      draftRevision = saved.draft_revision;
      $("draft-status").textContent = "Draft persisted on bridge. Not uploaded.";
    } catch (error) {
      draftFailed = true;
      $("draft-status").textContent = `Draft NOT saved: ${error.message}. Your edits remain in this page.`;
      throw error;
    }
  });
  saveQueue.catch(error => notify(error.message, true));
  return saveQueue;
}
function warning(points) {
  if (!points || points.length !== 10) return "Exactly ten hour/target slots are required; no automatic padding is performed.";
  let previous = -1;
  for (const [hour, target] of points) {
    if (!Number.isInteger(hour) || hour < 0 || hour > 23) return "Hours must be whole numbers 00-23.";
    if (hour <= previous) return "Duplicate or out-of-order hours: resolve explicitly before uploading this day.";
    previous = hour;
    if (!Number.isFinite(target) || (target !== 0 && (target < 7 || target > 40 || Math.abs(target * 10 - Math.round(target * 10)) > 1e-7)))
      return "Targets must be OFF (0) or 7-40 C in 0.1 C steps.";
  }
  return "";
}
function summarize(points) {
  return points ? points.map(([h, t]) => `${String(h).padStart(2, "0")}:00 ${t === 0 ? "OFF" : `${t} C`}`).join(" | ") : "No data";
}
function drawTimeline() {
  const points = pointsFor(day());
  const issue = warning(points);
  $("validation").textContent = issue;
  $("validation").className = issue ? "error" : "ok";
  $("timeline").replaceChildren();
  for (let hour = 0; hour < 24; hour++) {
    let target = null;
    if (points && !issue) {
      for (const [start, value] of points) if (start <= hour) target = value;
    }
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = `hour ${target === null ? "unknown" : target === 0 ? "off" : "on"}`;
    const time = document.createElement("span"); time.textContent = `${String(hour).padStart(2, "0")}:00`;
    const label = document.createElement("strong"); label.textContent = target === null ? "?" : target === 0 ? "OFF" : `${target} C`;
    cell.append(time, label); cell.title = target === null ? "Unknown interval; inspect point list" : `${time.textContent}: ${label.textContent}`;
    cell.disabled = !record || $("layer").value !== "draft";
    cell.addEventListener("click", () => {
      const key = day(), index = Number($("paint-slot").value);
      const next = clone(draft[key] || reported()[key] || Array.from({length: 10}, () => [null, null]));
      next[index] = [hour, $("paint-target").value === "" ? null : Number($("paint-target").value)];
      draft[key] = next; saveDraft(); renderSchedule();
    });
    $("timeline").append(cell);
  }
  $("week").replaceChildren();
  if ($("view").value === "weekly") {
    for (const key of DAYS.slice(1)) {
      const button = document.createElement("button"); button.className = "week-day";
      button.textContent = `${NAMES[key]}: ${summarize(pointsFor(key))}`;
      button.addEventListener("click", () => { $("day").value = key; renderSchedule(); });
      $("week").append(button);
    }
  }
}
function renderSchedule() {
  const key = day(), points = pointsFor(key);
  const editable = $("layer").value === "draft";
  $("slots").replaceChildren();
  for (let i = 0; i < 10; i++) {
    const box = document.createElement("div"); box.className = "slot";
    const heading = document.createElement("strong"); heading.textContent = `Slot ${i + 1}`; box.append(heading);
    for (const [index, title, min, max, step] of [[0, "Hour", 0, 23, 1], [1, "Target / 0=OFF", 0, 40, .1]]) {
      const label = document.createElement("label"); label.textContent = title;
      const input = document.createElement("input"); input.type = "number"; input.min = min; input.max = max; input.step = step;
      input.value = points?.[i]?.[index] ?? ""; input.disabled = !editable || !record;
      input.addEventListener("change", () => {
        const next = clone(draft[key] || reported()[key] || Array.from({length: 10}, () => [null, null]));
        next[i][index] = input.value === "" ? null : Number(input.value);
        draft[key] = next; saveDraft(); drawTimeline();
      });
      label.append(input); box.append(label);
    }
    $("slots").append(box);
  }
  drawTimeline();
}
function renderSettings() {
  $("settings").replaceChildren();
  for (const [key, index, name, limits] of controls) {
    const label = document.createElement("label"); label.className = "setting"; label.textContent = name;
    const value = draft[key] ?? reported()[key];
    const current = index === null ? value : value?.[index];
    const numeric = typeof limits[0] === "number";
    const input = document.createElement(numeric ? "input" : "select");
    if (numeric) {
      input.type = "number"; [input.min, input.max, input.step] = limits;
    } else {
      input.append(option("", "Unknown"), ...limits.map(v => option(v, v)));
    }
    input.value = current ?? "";
    input.disabled = !record || (index !== null && value === undefined && key !== "STU");
    input.addEventListener("change", () => {
      const chosen = numeric ? (input.value === "" ? null : Number(input.value)) : input.value;
      if (index === null) draft[key] = chosen;
      else { draft[key] = clone(draft[key] ?? reported()[key] ?? [null, null]); draft[key][index] = chosen; }
      saveDraft();
    });
    label.append(input); $("settings").append(label);
  }
}
function renderStatus() {
  if (!record) return;
  $("connection").textContent = record.online ? "Boiler reports fresh" : "Boiler stale / no parameter report";
  $("upload").textContent = `${record.command_state}. ${record.command_error || ""} Attempts: ${record.attempts}. ` +
    `Last report: ${record.last_report ? new Date(record.last_report * 1000).toLocaleString() : "none"}`;
  $("warnings").textContent = [...(record.schedule_warnings || []), ...(record.report?.parse_errors || []),
    ...(record.report?.stage_conflict ? ["ST1/ST2 disagree with STU. Resolve the duplicate flags before sending a complete settings response."] : [])].join("\n");
  $("snapshots").textContent = JSON.stringify({reported: reported(), pending: record.pending}, null, 2);
  $("readings").textContent = JSON.stringify({decoded: record.report?.decoded, separate_status: record.status}, null, 2);
}
async function selectBoiler() {
  await saveQueue.catch(() => {});
  if (draftFailed) throw new Error("Reload before switching devices; unsaved draft conflict needs resolution");
  serial = $("boiler").value;
  if (!serial) return;
  record = await api(endpoint()); draft = clone(record.draft); draftRevision = record.draft_revision;
  renderStatus(); renderSchedule(); renderSettings();
}
async function apply(schedules) {
  await saveQueue;
  if (draftFailed) throw new Error("Save draft before applying");
  const patch = Object.fromEntries(Object.entries(draft).filter(([key]) => DAYS.includes(key) === schedules));
  if (!Object.keys(patch).length) throw new Error("No draft changes in this section");
  if (schedules) for (const [key, points] of Object.entries(patch)) {
    const issue = warning(points); if (issue) throw new Error(`${key}: ${issue}`);
  }
  record = await api(`${endpoint()}/settings`, "POST", {settings: patch, revision: record.revision});
  renderStatus(); drawTimeline();
  notify("Queued, NOT yet applied. The next boiler poll uploads settings; a later report must confirm them.");
}
function action(id, callback) {
  $(id).addEventListener("click", () => Promise.resolve().then(callback).catch(error => notify(error.message, true)));
}
for (const key of DAYS) $("copy-source").append(option(key, NAMES[key]));
for (let index = 0; index < 10; index++) $("paint-slot").append(option(index, `Slot ${index + 1}`));
for (const key of DAYS.slice(1)) {
  const label = document.createElement("label"), input = document.createElement("input");
  input.type = "checkbox"; input.value = key; label.append(input, NAMES[key]); $("destinations").append(label);
}
$("view").addEventListener("change", () => {
  $("day").replaceChildren(...($("view").value === "daily" ? ["ED"] : DAYS.slice(1)).map(k => option(k, NAMES[k])));
  renderSchedule();
});
$("day").append(option("ED", NAMES.ED));
$("day").addEventListener("change", renderSchedule);
$("layer").addEventListener("change", renderSchedule);
$("boiler").addEventListener("change", () => selectBoiler().catch(error => notify(error.message, true)));
action("copy", async () => {
  const source = pointsFor($("copy-source").value, "draft");
  if (!source) throw new Error("Source day has no points");
  draft[day()] = clone(source); await saveDraft(); renderSchedule();
});
action("copy-many", async () => {
  const source = pointsFor(day(), "draft");
  if (!source) throw new Error("Selected day has no points");
  for (const input of $("destinations").querySelectorAll("input:checked")) draft[input.value] = clone(source);
  await saveDraft(); renderSchedule();
});
action("use-reported", async () => {
  if (!reported()[day()]) throw new Error("No reported schedule");
  draft[day()] = clone(reported()[day()]); await saveDraft(); renderSchedule();
});
action("clear-draft", async () => { draft = {}; await saveDraft(); renderSchedule(); renderSettings(); });
action("apply-schedules", () => apply(true));
action("apply-settings", () => apply(false));
action("cancel", async () => {
  record = await api(`${endpoint()}/cancel`, "POST", {});
  renderStatus(); notify("Pending retries cancelled. Already-delivered commands cannot be recalled.");
});
async function refresh() {
  if (!serial) {
    const devices = await api("/api/boilers");
    $("boiler").replaceChildren(...devices.map(d => option(d.serial, d.serial)));
    const requested = new URLSearchParams(location.search).get("serial");
    if (devices.some(d => d.serial === requested)) $("boiler").value = requested;
    await selectBoiler();
    if (!serial) notify("Waiting for the first boiler report.");
    return;
  }
  const fresh = await api(endpoint());
  // Never replace a draft or in-progress input when telemetry arrives.
  record = fresh; renderStatus();
  if ($("layer").value === "draft") drawTimeline();
  else renderSchedule();
}
refresh().catch(error => notify(error.message, true));
setInterval(() => refresh().catch(error => notify(error.message, true)), 5000);
