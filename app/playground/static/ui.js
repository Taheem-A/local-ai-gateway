"use strict";

/*
 * Pure presentation behavior for the local workbench.
 *
 * API calls intentionally remain in app.js. Keeping theme/navigation/inspector
 * behavior here prevents the visual shell from becoming coupled to gateway
 * request semantics.
 */

const WORKBENCH_THEME_KEY = "local-ai-workbench-theme";
const DEFAULT_THEME = "signal-red";
const THEMES = new Set([
  "signal-red",
  "copper",
  "emerald",
  "cyan",
  "violet",
  "rose",
  "lime",
  "espresso",
]);

const viewLabels = {
  generate: "Generate",
  extract: "Extract",
  classify: "Classify",
  rag: "RAG",
  tools: "Tools",
  debug: "Requests",
};

function byId(id) {
  return document.getElementById(id);
}

function safeStoredTheme() {
  try {
    const stored = localStorage.getItem(WORKBENCH_THEME_KEY);
    return THEMES.has(stored) ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

function applyTheme(theme, persist = true) {
  const selected = THEMES.has(theme) ? theme : DEFAULT_THEME;
  document.documentElement.dataset.theme = selected;
  const selector = byId("theme-select");
  if (selector) selector.value = selected;
  if (persist) {
    try {
      localStorage.setItem(WORKBENCH_THEME_KEY, selected);
    } catch {
      // Theme persistence is optional; the workbench must still function.
    }
  }
}

function setInspector(open) {
  document.body.classList.toggle("inspector-open", open);
  const toggle = byId("inspector-toggle");
  if (toggle) toggle.setAttribute("aria-pressed", String(open));
}

function activeViewName() {
  const active = document.querySelector(".nav-item.active[data-view]");
  return active?.dataset.view || "generate";
}

function syncPageTitle() {
  const name = activeViewName();
  const title = byId("page-title");
  if (title) title.textContent = viewLabels[name] || name;
}

function runCommand(rawCommand) {
  const command = rawCommand.trim().toLowerCase();
  if (!command) return;

  const aliases = {
    generate: "generate",
    gen: "generate",
    extract: "extract",
    classify: "classify",
    classification: "classify",
    rag: "rag",
    search: "rag",
    tools: "tools",
    tool: "tools",
    requests: "debug",
    request: "debug",
    logs: "debug",
  };

  if (aliases[command]) {
    document.querySelector(`.nav-item[data-view="${aliases[command]}"]`)?.click();
    return;
  }
  if (command === "inspector") {
    setInspector(!document.body.classList.contains("inspector-open"));
    return;
  }
  if (command === "refresh" || command === "status") {
    byId("refresh-all")?.click();
    return;
  }
  if (command === "connect") {
    byId("connect-button")?.click();
  }
}

function submitActiveView() {
  const name = activeViewName();
  const formByView = {
    generate: "generate-form",
    extract: "extract-form",
    classify: "classify-form",
    rag: "rag-form",
    tools: "tools-form",
  };
  const form = byId(formByView[name]);
  if (form && typeof form.requestSubmit === "function") form.requestSubmit();
}

function metaValue(label) {
  const items = byId("generate-meta")?.querySelectorAll(".meta-item") || [];
  for (const item of items) {
    const key = item.querySelector("span")?.textContent?.trim().toLowerCase();
    if (key === label) return item.querySelector("strong")?.textContent?.trim() || null;
  }
  return null;
}

function syncRuntimeStatus() {
  const firstText = metaValue("first text");
  const tps = metaValue("tokens / sec");
  const output = metaValue("output tokens");
  const latency = metaValue("total latency");

  if (byId("status-first-text")) byId("status-first-text").textContent = `TTFT ${firstText || "—"}`;
  if (byId("status-tps")) byId("status-tps").textContent = `${tps || "—"} tok/s`;
  if (byId("status-output-tokens")) byId("status-output-tokens").textContent = `${output || "—"} tokens`;
  if (byId("status-latency")) byId("status-latency").textContent = latency || "— s";
}

function syncStreamingState() {
  const text = byId("generate-state")?.textContent?.toLowerCase() || "";
  const pane = document.querySelector("#view-generate .response-pane");
  pane?.classList.toggle("streaming", text.includes("streaming") || text.includes("model loading") || text.includes("prompt processing") || text.includes("starting"));
}

function shortSource(hit) {
  return hit.source || hit.document_id || "unknown source";
}

function renderRetrievalHits(hits) {
  const target = byId("rag-results");
  const count = byId("rag-result-count");
  if (!target || !count) return;
  target.replaceChildren();
  count.textContent = `${hits.length} result${hits.length === 1 ? "" : "s"}`;

  if (!hits.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No matching chunks returned.";
    target.append(empty);
    return;
  }

  for (const hit of hits) {
    const row = document.createElement("div");
    row.className = "retrieval-hit";

    const rank = document.createElement("span");
    rank.className = "retrieval-rank";
    rank.textContent = String(hit.rank ?? "—").padStart(2, "0");

    const score = document.createElement("span");
    score.className = "retrieval-score";
    score.textContent = Number.isFinite(Number(hit.score)) ? Number(hit.score).toFixed(3) : "—";

    const source = document.createElement("span");
    source.className = "retrieval-source";
    source.textContent = shortSource(hit);

    const excerpt = document.createElement("span");
    excerpt.className = "retrieval-text";
    excerpt.textContent = hit.text || "";

    row.append(rank, score, source, excerpt);
    target.append(row);
  }
}

function renderCitations(citations) {
  const target = byId("rag-citations");
  if (!target) return;
  target.replaceChildren();

  if (!citations.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state small";
    empty.textContent = "No citations returned.";
    target.append(empty);
    return;
  }

  for (const citation of citations) {
    const row = document.createElement("div");
    row.className = "citation-row";

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = citation.label || "—";

    const source = document.createElement("span");
    source.className = "source";
    source.textContent = citation.source || citation.document_id || "unknown source";

    const score = document.createElement("span");
    score.className = "score";
    score.textContent = Number.isFinite(Number(citation.score)) ? Number(citation.score).toFixed(3) : "—";

    row.append(label, source, score);
    target.append(row);
  }
}

function syncRagPresentation() {
  const raw = byId("rag-output")?.textContent?.trim();
  if (!raw || raw === "Waiting for a request.") return;

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return;
  }

  const hits = Array.isArray(payload.hits)
    ? payload.hits
    : (Array.isArray(payload.retrieved) ? payload.retrieved : []);
  renderRetrievalHits(hits);

  const answer = byId("rag-answer");
  if (answer) {
    answer.replaceChildren();
    const text = document.createElement("div");
    if (typeof payload.answer === "string" && payload.answer.trim()) {
      text.textContent = payload.answer;
    } else if (payload.hits) {
      text.className = "empty-state";
      text.textContent = "Search mode returned retrieval hits. Switch to answer mode for grounded generation.";
    } else {
      text.className = "empty-state";
      text.textContent = "No grounded answer returned.";
    }
    answer.append(text);
  }

  renderCitations(Array.isArray(payload.citations) ? payload.citations : []);
}

function enhanceRequestRows() {
  const body = byId("requests-body");
  if (!body) return;
  for (const row of body.querySelectorAll("tr")) {
    if (row.dataset.enhanced === "true" || row.children.length < 8) continue;
    row.dataset.enhanced = "true";
    row.addEventListener("click", () => {
      body.querySelectorAll("tr.selected").forEach((item) => item.classList.remove("selected"));
      row.classList.add("selected");
      const cells = [...row.children].map((cell) => cell.textContent?.trim() || "");
      const metadata = {
        time: cells[0],
        endpoint: cells[1],
        project: cells[2],
        profile: cells[3],
        model: cells[4],
        latency: cells[5],
        tokens: cells[6],
        status: cells[7],
        privacy_note: "Operational metrics only; request/response content is intentionally not stored.",
      };
      if (byId("inspector-endpoint")) byId("inspector-endpoint").textContent = cells[1] || "Request metadata";
      if (byId("inspector-request")) byId("inspector-request").textContent = JSON.stringify(metadata, null, 2);
      if (byId("inspector-response")) byId("inspector-response").textContent = "Content unavailable by design. The metrics database never stores prompts, generated text, RAG evidence, tool arguments, or secrets.";
      setInspector(true);
    });
  }
}

function wirePresentation() {
  applyTheme(safeStoredTheme(), false);
  byId("theme-select")?.addEventListener("change", (event) => applyTheme(event.target.value));

  byId("inspector-toggle")?.addEventListener("click", () => {
    setInspector(!document.body.classList.contains("inspector-open"));
  });
  byId("inspector-close")?.addEventListener("click", () => setInspector(false));

  document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
    button.addEventListener("click", () => window.setTimeout(syncPageTitle, 0));
  });

  const command = byId("command-input");
  command?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runCommand(command.value);
      command.value = "";
      command.blur();
    } else if (event.key === "Escape") {
      command.value = "";
      command.blur();
    }
  });

  document.addEventListener("keydown", (event) => {
    const commandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
    if (commandShortcut) {
      event.preventDefault();
      command?.focus();
      command?.select();
      return;
    }
    if (event.ctrlKey && event.key === "Enter") {
      event.preventDefault();
      submitActiveView();
      return;
    }
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "i") {
      event.preventDefault();
      setInspector(!document.body.classList.contains("inspector-open"));
    }
  });

  const meta = byId("generate-meta");
  if (meta) new MutationObserver(syncRuntimeStatus).observe(meta, { childList: true, subtree: true, characterData: true });

  const generationState = byId("generate-state");
  if (generationState) new MutationObserver(syncStreamingState).observe(generationState, { childList: true, subtree: true, characterData: true });

  const ragOutput = byId("rag-output");
  if (ragOutput) new MutationObserver(syncRagPresentation).observe(ragOutput, { childList: true, subtree: true, characterData: true });

  const requestBody = byId("requests-body");
  if (requestBody) new MutationObserver(enhanceRequestRows).observe(requestBody, { childList: true, subtree: true });

  syncPageTitle();
  syncRuntimeStatus();
  syncStreamingState();
  enhanceRequestRows();
}

document.addEventListener("DOMContentLoaded", wirePresentation);
