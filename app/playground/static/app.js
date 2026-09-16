"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  connected: false,
  status: null,
  streamController: null,
  lastRequest: {},
  lastResponse: {},
  lastEndpoint: "Nothing sent yet.",
};

function value(id) {
  return $(id).value.trim();
}

function optionalValue(id) {
  const current = value(id);
  return current || null;
}

function numberValue(id) {
  return Number($(id).value);
}

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function showToast(message, error = false) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function setConnection(mode, message) {
  const pill = $("connection-pill");
  pill.classList.remove("pill-online", "pill-offline", "pill-error");
  if (mode === "online") {
    pill.classList.add("pill-online");
    pill.textContent = message || "Connected";
    state.connected = true;
  } else if (mode === "error") {
    pill.classList.add("pill-error");
    pill.textContent = message || "Connection failed";
    state.connected = false;
  } else {
    pill.classList.add("pill-offline");
    pill.textContent = message || "Disconnected";
    state.connected = false;
  }
}

function currentKey() {
  return value("api-key") || sessionStorage.getItem("local-ai-key") || "";
}

function apiHeaders(json = true) {
  const key = currentKey();
  if (!key) {
    throw new Error("Enter the gateway API key and connect first.");
  }
  const headers = { "X-Local-AI-Key": key };
  const project = value("project-id");
  if (project) headers["X-Project-ID"] = project;
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

function setInspector(endpoint, requestBody, responseBody) {
  state.lastEndpoint = endpoint;
  state.lastRequest = requestBody ?? {};
  state.lastResponse = responseBody ?? {};
  $("inspector-endpoint").textContent = endpoint;
  $("inspector-request").textContent = pretty(state.lastRequest);
  $("inspector-response").textContent = pretty(state.lastResponse);
}

function updateInspectorResponse(responseBody) {
  state.lastResponse = responseBody ?? {};
  $("inspector-response").textContent = pretty(state.lastResponse);
}

function extractError(payload, fallback) {
  if (payload && payload.error) {
    const error = payload.error;
    let message = `${error.code || "ERROR"}: ${error.message || fallback}`;
    if (error.details) message += `\n${pretty(error.details)}`;
    return message;
  }
  return fallback;
}

async function apiJson(path, { method = "GET", body = null, inspect = true } = {}) {
  if (inspect) setInspector(`${method} ${path}`, body ?? {}, { state: "pending" });
  const response = await fetch(path, {
    method,
    headers: apiHeaders(body !== null),
    body: body === null ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text };
    }
  }
  if (!response.ok) {
    if (inspect) updateInspectorResponse(payload || { status: response.status });
    throw new Error(extractError(payload, `HTTP ${response.status}`));
  }
  if (inspect) updateInspectorResponse(payload || {});
  return payload;
}

function commonProfile(prefix) {
  const payload = { quality: value(`${prefix}-quality`) };
  const reasoning = value(`${prefix}-reasoning`);
  if (reasoning) payload.reasoning = reasoning;
  return payload;
}

function renderStatus(status) {
  state.status = status;
  $("lm-status").textContent = status.lmstudio || "unknown";
  $("loaded-model-count").textContent = String((status.loaded_models || []).length);
  $("embedding-model").textContent = status.embedding_model || "—";

  const container = $("status-cards");
  container.replaceChildren();
  const cards = [
    ["Gateway", status.gateway || "ok"],
    ["LM Studio", status.lmstudio || "unknown"],
    ["Loaded models", (status.loaded_models || []).length],
    ["Embedding", status.embedding_model || "—"],
  ];
  for (const [label, current] of cards) {
    const card = document.createElement("div");
    card.className = "dashboard-card";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(current);
    card.append(span, strong);
    container.append(card);
  }
  $("profiles-output").textContent = pretty(status.profiles || {});
}

async function connect({ quiet = false } = {}) {
  const key = currentKey();
  if (!key) {
    if (!quiet) showToast("Enter the gateway API key first.", true);
    return false;
  }
  setConnection("offline", "Connecting…");
  try {
    const status = await apiJson("/v1/status", { inspect: false });
    sessionStorage.setItem("local-ai-key", key);
    const project = value("project-id");
    if (project) sessionStorage.setItem("local-ai-project", project);
    else sessionStorage.removeItem("local-ai-project");
    setConnection("online", status.lmstudio === "ok" ? "Connected" : "Gateway only");
    renderStatus(status);
    await Promise.allSettled([loadCollections(), refreshDebug()]);
    if (!quiet) showToast("Connected to the local gateway.");
    return true;
  } catch (error) {
    setConnection("error", "Connection failed");
    if (!quiet) showToast(error.message, true);
    return false;
  }
}

function clearSession() {
  sessionStorage.removeItem("local-ai-key");
  sessionStorage.removeItem("local-ai-project");
  $("api-key").value = "";
  $("project-id").value = "";
  state.status = null;
  setConnection("offline");
  $("lm-status").textContent = "—";
  $("loaded-model-count").textContent = "—";
  $("embedding-model").textContent = "—";
  showToast("Playground session cleared.");
}

function switchView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.remove("active"));
  $(`view-${name}`).classList.add("active");
  document.querySelector(`.nav-item[data-view="${name}"]`).classList.add("active");
  if (name === "debug" && state.connected) refreshDebug();
}

function renderMeta(targetId, data) {
  const target = $(targetId);
  target.replaceChildren();
  const entries = [
    ["model", data.model],
    ["profile", data.profile],
    ["reasoning", data.reasoning],
    ["input tokens", data.input_tokens],
    ["output tokens", data.output_tokens],
    ["reasoning tokens", data.reasoning_output_tokens],
    ["first text", data.time_to_first_text_seconds == null ? null : `${Number(data.time_to_first_text_seconds).toFixed(3)} s`],
    ["total latency", data.total_latency_seconds == null ? null : `${Number(data.total_latency_seconds).toFixed(3)} s`],
    ["tokens / sec", data.tokens_per_second == null ? null : Number(data.tokens_per_second).toFixed(2)],
    ["request id", data.request_id],
  ];
  for (const [label, current] of entries) {
    if (current === undefined || current === null) continue;
    const item = document.createElement("div");
    item.className = "meta-item";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(current);
    strong.title = String(current);
    item.append(span, strong);
    target.append(item);
  }
}

function parseSseFrame(frame) {
  let eventName = "message";
  const dataLines = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  return { eventName, data: JSON.parse(dataLines.join("\n")) };
}

async function consumeSse(response, onEvent) {
  if (!response.body) throw new Error("Streaming response body was unavailable.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value: chunk, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(chunk, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (frame) {
        const parsed = parseSseFrame(frame);
        if (parsed) await onEvent(parsed.eventName, parsed.data);
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
  buffer += decoder.decode().replace(/\r\n/g, "\n");
  if (buffer.trim()) {
    const parsed = parseSseFrame(buffer.trim());
    if (parsed) await onEvent(parsed.eventName, parsed.data);
  }
}

async function runGenerate(event) {
  event.preventDefault();
  const body = {
    prompt: value("generate-prompt"),
    system: optionalValue("generate-system"),
    ...commonProfile("generate"),
    temperature: numberValue("generate-temperature"),
    max_output_tokens: numberValue("generate-max-tokens"),
  };
  if (body.system === null) delete body.system;

  const output = $("generate-output");
  output.textContent = "";
  output.classList.remove("empty");
  $("generate-meta").replaceChildren();

  if (!$("generate-stream").checked) {
    $("generate-state").textContent = "Running…";
    try {
      const result = await apiJson("/v1/generate", { method: "POST", body });
      output.textContent = result.text || "";
      renderMeta("generate-meta", result);
      $("generate-state").textContent = "Completed";
    } catch (error) {
      output.textContent = error.message;
      $("generate-state").textContent = "Failed";
      showToast(error.message, true);
    }
    return;
  }

  const endpoint = "POST /v1/generate/stream";
  const events = [];
  setInspector(endpoint, body, { state: "streaming", events: [] });
  $("generate-state").textContent = "Starting stream…";
  $("stop-stream").classList.remove("hidden");
  state.streamController = new AbortController();

  try {
    const response = await fetch("/v1/generate/stream", {
      method: "POST",
      headers: apiHeaders(true),
      body: JSON.stringify(body),
      signal: state.streamController.signal,
    });
    if (!response.ok) {
      let payload = null;
      try { payload = await response.json(); } catch { payload = null; }
      updateInspectorResponse(payload || { status: response.status });
      throw new Error(extractError(payload, `HTTP ${response.status}`));
    }

    let deltaCount = 0;
    await consumeSse(response, async (eventName, data) => {
      events.push({ event: eventName, data });
      if (eventName === "progress") {
        const phase = String(data.phase || "working").replaceAll("_", " ");
        const progress = data.progress == null ? "" : ` ${Math.round(Number(data.progress) * 100)}%`;
        $("generate-state").textContent = `${phase}${progress}`;
      } else if (eventName === "delta") {
        output.textContent += data.text || "";
        deltaCount += 1;
        $("generate-state").textContent = `Streaming · ${deltaCount} deltas`;
      } else if (eventName === "completed") {
        if (output.textContent !== (data.text || "")) output.textContent = data.text || output.textContent;
        renderMeta("generate-meta", data);
        $("generate-state").textContent = "Completed";
      } else if (eventName === "error") {
        throw new Error(extractError(data, "The stream failed."));
      }
      if (events.length < 20 || events.length % 25 === 0 || eventName === "completed") {
        updateInspectorResponse({ event_count: events.length, events });
      }
    });
    updateInspectorResponse({ event_count: events.length, events });
  } catch (error) {
    if (error.name === "AbortError") {
      $("generate-state").textContent = "Stopped";
      updateInspectorResponse({ event_count: events.length, stopped_by_user: true, events });
      showToast("Stream stopped.");
    } else {
      $("generate-state").textContent = "Failed";
      if (!output.textContent) output.textContent = error.message;
      showToast(error.message, true);
    }
  } finally {
    state.streamController = null;
    $("stop-stream").classList.add("hidden");
  }
}

async function runExtract(event) {
  event.preventDefault();
  try {
    const body = {
      prompt: value("extract-prompt"),
      schema: JSON.parse(value("extract-schema")),
      system: optionalValue("extract-system"),
      ...commonProfile("extract"),
      max_output_tokens: numberValue("extract-max-tokens"),
      max_attempts: numberValue("extract-attempts"),
    };
    if (body.system === null) delete body.system;
    const result = await apiJson("/v1/extract", { method: "POST", body });
    $("extract-output").textContent = pretty(result);
  } catch (error) {
    $("extract-output").textContent = error.message;
    showToast(error.message, true);
  }
}

function parseLabels(text) {
  return text.split(/[\n,]/).map((label) => label.trim()).filter(Boolean);
}

async function runClassify(event) {
  event.preventDefault();
  try {
    const body = {
      text: value("classify-text"),
      labels: parseLabels(value("classify-labels")),
      system: optionalValue("classify-system"),
      ...commonProfile("classify"),
      max_output_tokens: numberValue("classify-max-tokens"),
      max_attempts: numberValue("classify-attempts"),
    };
    if (body.system === null) delete body.system;
    const result = await apiJson("/v1/classify", { method: "POST", body });
    $("classify-output").textContent = pretty(result);
  } catch (error) {
    $("classify-output").textContent = error.message;
    showToast(error.message, true);
  }
}

function parseOptionalObject(text) {
  const raw = text.trim();
  if (!raw) return null;
  const parsed = JSON.parse(raw);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && Object.keys(parsed).length === 0) return null;
  return parsed;
}

async function loadCollections() {
  if (!currentKey()) return;
  try {
    const result = await apiJson("/v1/rag/collections", { inspect: false });
    const target = $("rag-collections");
    target.replaceChildren();
    const collections = result.collections || [];
    if (!collections.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No indexed collections yet.";
      target.append(empty);
      return;
    }
    for (const collection of collections) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.textContent = `${collection.collection} · ${collection.documents} docs · ${collection.chunks} chunks`;
      button.addEventListener("click", () => { $("rag-collection").value = collection.collection; });
      target.append(button);
    }
  } catch (error) {
    $("rag-collections").textContent = error.message;
  }
}

async function runRag(event) {
  event.preventDefault();
  try {
    const body = {
      collection: value("rag-collection"),
      query: value("rag-query"),
      top_k: numberValue("rag-top-k"),
      min_score: numberValue("rag-min-score"),
    };
    const metadataFilter = parseOptionalObject(value("rag-filter"));
    if (metadataFilter) body.metadata_filter = metadataFilter;
    const mode = value("rag-mode");
    let endpoint = "/v1/rag/search";
    if (mode === "answer") {
      endpoint = "/v1/rag/answer";
      Object.assign(body, commonProfile("rag"));
      body.max_output_tokens = 2048;
    }
    const result = await apiJson(endpoint, { method: "POST", body });
    $("rag-output").textContent = pretty(result);
  } catch (error) {
    $("rag-output").textContent = error.message;
    showToast(error.message, true);
  }
}

async function runTools(event) {
  event.preventDefault();
  try {
    const body = {
      messages: JSON.parse(value("tools-messages")),
      tools: JSON.parse(value("tools-definitions")),
      system: optionalValue("tools-system"),
      ...commonProfile("tools"),
      tool_choice: value("tools-choice"),
      temperature: 0,
      max_output_tokens: numberValue("tools-max-tokens"),
    };
    if (body.system === null) delete body.system;
    const result = await apiJson("/v1/tools/turn", { method: "POST", body });
    $("tools-output").textContent = pretty(result);
  } catch (error) {
    $("tools-output").textContent = error.message;
    showToast(error.message, true);
  }
}

function renderMetrics(metrics) {
  const target = $("metrics-summary");
  target.replaceChildren();
  const rows = [
    ["Requests", metrics.requests],
    ["Success rate", metrics.success_rate_percent == null ? "—" : `${metrics.success_rate_percent}%`],
    ["Mean latency", metrics.mean_latency_seconds == null ? "—" : `${metrics.mean_latency_seconds}s`],
    ["Input tokens", metrics.input_tokens],
    ["Output tokens", metrics.output_tokens],
    ["Reasoning tokens", metrics.reasoning_tokens],
  ];
  for (const [label, current] of rows) {
    const item = document.createElement("div");
    item.className = "metric";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(current ?? "—");
    item.append(span, strong);
    target.append(item);
  }
}

function renderRequests(requests) {
  const body = $("requests-body");
  body.replaceChildren();
  if (!requests.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.className = "muted";
    cell.textContent = "No metrics recorded yet.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const request of requests) {
    const row = document.createElement("tr");
    const timestamp = request.timestamp ? new Date(request.timestamp).toLocaleString() : "—";
    const tokens = `${request.input_tokens ?? "—"}/${request.reasoning_tokens ?? "—"}/${request.output_tokens ?? "—"}`;
    const latency = request.total_latency_seconds == null ? "—" : `${Number(request.total_latency_seconds).toFixed(3)}s`;
    const cells = [timestamp, request.endpoint, request.project || "—", request.quality || "—", request.model || "—", latency, tokens];
    for (const current of cells) {
      const cell = document.createElement("td");
      cell.textContent = String(current);
      row.append(cell);
    }
    const result = document.createElement("td");
    result.className = request.success ? "result-good" : "result-bad";
    result.textContent = request.success ? "success" : (request.error_code || "failed");
    row.append(result);
    body.append(row);
  }
}

async function refreshDebug() {
  if (!currentKey()) return;
  const days = Math.max(1, Math.min(365, numberValue("metrics-days") || 7));
  const limit = Math.max(1, Math.min(200, numberValue("request-limit") || 50));
  try {
    const [status, metrics, requests] = await Promise.all([
      apiJson("/v1/status", { inspect: false }),
      apiJson(`/v1/debug/metrics?days=${days}`, { inspect: false }),
      apiJson(`/v1/debug/requests?limit=${limit}`, { inspect: false }),
    ]);
    renderStatus(status);
    renderMetrics(metrics);
    renderRequests(requests.requests || []);
    if (state.connected) setConnection("online", status.lmstudio === "ok" ? "Connected" : "Gateway only");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast("Copied to clipboard.");
  } catch {
    showToast("Clipboard access was unavailable.", true);
  }
}

function wireEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  $("connect-button").addEventListener("click", () => connect());
  $("clear-session").addEventListener("click", clearSession);
  $("refresh-all").addEventListener("click", async () => {
    if (!currentKey()) return showToast("Connect first.", true);
    await Promise.allSettled([connect({ quiet: true }), loadCollections(), refreshDebug()]);
    showToast("Status refreshed.");
  });
  $("generate-form").addEventListener("submit", runGenerate);
  $("stop-stream").addEventListener("click", () => state.streamController?.abort());
  $("extract-form").addEventListener("submit", runExtract);
  $("classify-form").addEventListener("submit", runClassify);
  $("rag-form").addEventListener("submit", runRag);
  $("tools-form").addEventListener("submit", runTools);
  $("rag-refresh-collections").addEventListener("click", loadCollections);
  $("debug-refresh").addEventListener("click", refreshDebug);
  $("copy-request").addEventListener("click", () => copyText(pretty(state.lastRequest)));
  $("copy-response").addEventListener("click", () => copyText(pretty(state.lastResponse)));
  $("project-id").addEventListener("change", () => {
    const project = value("project-id");
    if (project) sessionStorage.setItem("local-ai-project", project);
    else sessionStorage.removeItem("local-ai-project");
  });
}

async function boot() {
  wireEvents();
  const savedKey = sessionStorage.getItem("local-ai-key") || "";
  const savedProject = sessionStorage.getItem("local-ai-project") || "";
  $("api-key").value = savedKey;
  $("project-id").value = savedProject;
  if (savedKey) await connect({ quiet: true });
}

document.addEventListener("DOMContentLoaded", boot);
