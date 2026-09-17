"use strict";

/* Stage 5 Vision workbench extension.
 *
 * The panel is injected into the existing zero-build shell so the Stage 4
 * layout/theme system stays untouched. Requests still use the real gateway
 * endpoint; image bytes never enter debug metrics or browser persistence.
 */

(() => {
  if (document.getElementById("view-vision")) return;

  const toolsNav = document.querySelector('.nav-item[data-view="tools"]');
  const toolsView = document.getElementById("view-tools");
  if (!toolsNav || !toolsView) return;

  const nav = document.createElement("button");
  nav.className = "nav-item";
  nav.dataset.view = "vision";
  nav.type = "button";
  nav.innerHTML = '<span class="nav-glyph">◫</span><span>Vision</span>';
  toolsNav.before(nav);

  const section = document.createElement("section");
  section.className = "view";
  section.id = "view-vision";
  section.innerHTML = `
    <div class="pane-grid vision-grid">
      <section class="pane request-pane">
        <div class="pane-header">
          <div>
            <h2>Vision</h2>
            <p>Inspect screenshots, photos, diagrams, and document images locally.</p>
          </div>
          <span id="vision-capability" class="runtime-state">VLM</span>
        </div>
        <form id="vision-form" class="pane-form">
          <label class="vision-upload-label">Images <span class="muted">PNG, JPEG, WebP · up to 4</span>
            <input id="vision-files" class="vision-file-input" type="file" accept="image/png,image/jpeg,image/webp" multiple required>
          </label>
          <div id="vision-file-list" class="vision-file-list">
            <div class="empty-state">Choose one or more local images. Nothing is uploaded anywhere except your localhost gateway.</div>
          </div>
          <label>Prompt
            <textarea id="vision-prompt" rows="7" required>Explain the important information in these images. Be precise, and distinguish what is visible from what you infer.</textarea>
          </label>
          <details class="advanced-block">
            <summary>Advanced options</summary>
            <div class="advanced-content">
              <label>System <span class="muted">optional</span><textarea id="vision-system" rows="3" placeholder="Additional multimodal instruction"></textarea></label>
              <div class="toolbar-controls two">
                <label>Temperature<input id="vision-temperature" type="number" min="0" max="1" step="0.1" value="0.1"></label>
                <label>Max output tokens<input id="vision-max-tokens" type="number" min="1" max="8192" value="2048"></label>
              </div>
            </div>
          </details>
          <div class="vision-privacy-note">The gateway corrects orientation, strips image metadata, and downsizes oversized inputs before local inference.</div>
          <div class="form-actions"><span class="muted mono">Ctrl+Enter to run</span><button class="button button-primary run-button" type="submit">▶ Run vision</button></div>
        </form>
      </section>
      <section class="pane response-pane">
        <div class="pane-header response-header"><div><h2>Response</h2><p>Visible model output and preprocessing metadata.</p></div><span id="vision-state" class="runtime-state">Idle</span></div>
        <div class="response-tabs vision-response-tabs" role="tablist" aria-label="Vision response view">
          <button id="vision-tab-rendered" class="active" type="button" role="tab" aria-selected="true">Rendered</button>
          <button id="vision-tab-raw" type="button" role="tab" aria-selected="false">Raw</button>
          <span class="response-tab-label">Metrics</span>
        </div>
        <div id="vision-output" class="prose-output empty">Vision response will appear here.</div>
        <pre id="vision-output-raw" class="json-output code-surface hidden" aria-label="Raw Markdown output"></pre>
        <div id="vision-meta" class="meta-strip"></div>
        <details class="raw-result"><summary>Image preprocessing</summary><pre id="vision-image-meta" class="json-output code-surface">No images processed yet.</pre></details>
      </section>
    </div>`;
  toolsView.before(section);

  const filesInput = document.getElementById("vision-files");
  const fileList = document.getElementById("vision-file-list");
  const form = document.getElementById("vision-form");
  const output = document.getElementById("vision-output");
  const rawOutput = document.getElementById("vision-output-raw");
  const renderedTab = document.getElementById("vision-tab-rendered");
  const rawTab = document.getElementById("vision-tab-raw");
  const stateLabel = document.getElementById("vision-state");
  let previewUrls = [];
  let lastMarkdown = "";

  function selectVisionView() {
    if (typeof switchView === "function") switchView("vision");
    window.setTimeout(() => {
      const title = document.getElementById("page-title");
      if (title) title.textContent = "Vision";
    }, 20);
  }

  nav.addEventListener("click", selectVisionView);

  function setOutputMode(mode) {
    const raw = mode === "raw";
    output.classList.toggle("hidden", raw);
    rawOutput.classList.toggle("hidden", !raw);
    renderedTab.classList.toggle("active", !raw);
    rawTab.classList.toggle("active", raw);
    renderedTab.setAttribute("aria-selected", String(!raw));
    rawTab.setAttribute("aria-selected", String(raw));
  }

  renderedTab.addEventListener("click", () => setOutputMode("rendered"));
  rawTab.addEventListener("click", () => setOutputMode("raw"));

  function renderMarkdown(text) {
    lastMarkdown = String(text || "");
    rawOutput.textContent = lastMarkdown;
    output.classList.remove("empty", "vision-error-output");
    if (window.PlaygroundMarkdown?.mount) {
      window.PlaygroundMarkdown.mount(output, lastMarkdown);
    } else {
      output.textContent = lastMarkdown;
    }
  }

  function renderVisionFailure(error, status) {
    lastMarkdown = "";
    rawOutput.textContent = "";
    output.replaceChildren();
    output.classList.remove("empty");
    output.classList.add("vision-error-output");

    const title = document.createElement("h3");
    title.textContent = error?.code || `HTTP ${status}`;
    const message = document.createElement("p");
    message.textContent = error?.message || "The vision request failed.";
    output.append(title, message);

    const advisory = error?.details?.advisory;
    if (advisory) {
      const panel = document.createElement("div");
      panel.className = "vision-error-advisory";
      const heading = document.createElement("strong");
      heading.textContent = advisory.summary || "Suggested fix";
      const action = document.createElement("p");
      action.textContent = advisory.suggested_action || "";
      panel.append(heading, action);
      output.append(panel);
    }

    if (error?.details) {
      const details = document.createElement("details");
      details.className = "vision-error-details";
      const summary = document.createElement("summary");
      summary.textContent = "Technical details";
      const pre = document.createElement("pre");
      pre.className = "json-output code-surface";
      pre.textContent = JSON.stringify(error.details, null, 2);
      details.append(summary, pre);
      output.append(details);
    }
    setOutputMode("rendered");
  }

  function clearPreviews() {
    for (const url of previewUrls) URL.revokeObjectURL(url);
    previewUrls = [];
  }

  function renderFiles() {
    clearPreviews();
    fileList.replaceChildren();
    const files = [...filesInput.files].slice(0, 4);
    if (!files.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "Choose one or more local images. Nothing is persisted by the playground.";
      fileList.append(empty);
      return;
    }
    for (const file of files) {
      const row = document.createElement("div");
      row.className = "vision-file-row";
      const image = document.createElement("img");
      image.className = "vision-thumb";
      image.alt = "Selected local image preview";
      const url = URL.createObjectURL(file);
      previewUrls.push(url);
      image.src = url;
      const info = document.createElement("div");
      info.className = "vision-file-info";
      const name = document.createElement("strong");
      name.textContent = file.name;
      const meta = document.createElement("span");
      meta.className = "muted mono";
      meta.textContent = `${file.type || "unknown"} · ${(file.size / 1024).toFixed(1)} KB`;
      info.append(name, meta);
      row.append(image, info);
      fileList.append(row);
    }
    if (filesInput.files.length > 4 && typeof showToast === "function") {
      showToast("Stage 5 accepts at most four images per request.", true);
    }
  }

  filesInput.addEventListener("change", renderFiles);

  function fileAsGatewayImage(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
      reader.onload = () => {
        const value = String(reader.result || "");
        const marker = ";base64,";
        const index = value.indexOf(marker);
        if (index < 0) return reject(new Error(`${file.name} could not be encoded.`));
        resolve({ media_type: file.type, data_base64: value.slice(index + marker.length) });
      };
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const files = [...filesInput.files].slice(0, 4);
    if (!files.length) {
      if (typeof showToast === "function") showToast("Choose at least one image.", true);
      return;
    }
    const allowed = new Set(["image/png", "image/jpeg", "image/webp"]);
    const unsupported = files.find((file) => !allowed.has(file.type));
    if (unsupported) {
      if (typeof showToast === "function") showToast("Vision supports PNG, JPEG, and WebP only.", true);
      return;
    }

    stateLabel.textContent = "Preparing…";
    lastMarkdown = "";
    output.textContent = "";
    rawOutput.textContent = "";
    output.classList.remove("empty", "vision-error-output");
    setOutputMode("rendered");
    document.getElementById("vision-meta").replaceChildren();
    try {
      const images = await Promise.all(files.map(fileAsGatewayImage));
      const system = document.getElementById("vision-system").value.trim();
      const body = {
        prompt: document.getElementById("vision-prompt").value.trim(),
        images,
        temperature: Number(document.getElementById("vision-temperature").value),
        max_output_tokens: Number(document.getElementById("vision-max-tokens").value),
      };
      if (system) body.system = system;

      const safeInspectorBody = {
        ...body,
        images: files.map((file) => ({ name: file.name, media_type: file.type, bytes: file.size })),
      };
      if (typeof setInspector === "function") {
        setInspector("POST /v1/vision", safeInspectorBody, { state: "pending" });
      }
      stateLabel.textContent = "Running…";
      const response = await fetch("/v1/vision", {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify(body),
      });
      let payload = null;
      try { payload = await response.json(); } catch { payload = null; }
      if (!response.ok) {
        if (typeof updateInspectorResponse === "function") updateInspectorResponse(payload || { status: response.status });
        renderVisionFailure(payload?.error, response.status);
        stateLabel.textContent = "Failed";
        const toastText = payload?.error?.message || `Vision request failed with HTTP ${response.status}.`;
        if (typeof showToast === "function") showToast(toastText, true);
        return;
      }
      if (typeof updateInspectorResponse === "function") updateInspectorResponse(payload || {});
      renderMarkdown(payload.text || "");
      renderMeta("vision-meta", payload);
      document.getElementById("vision-image-meta").textContent = JSON.stringify(payload.images || [], null, 2);
      stateLabel.textContent = "Completed";
    } catch (error) {
      renderVisionFailure({ code: "PLAYGROUND_ERROR", message: error.message }, 0);
      stateLabel.textContent = "Failed";
      if (typeof showToast === "function") showToast(error.message, true);
    }
  });

  document.addEventListener("keydown", (event) => {
    const active = document.querySelector('.nav-item.active[data-view="vision"]');
    if (active && event.ctrlKey && event.key === "Enter") {
      event.preventDefault();
      event.stopImmediatePropagation();
      form.requestSubmit();
    }
  }, true);

  const command = document.getElementById("command-input");
  command?.addEventListener("keydown", (event) => {
    const value = command.value.trim().toLowerCase();
    if (event.key === "Enter" && ["vision", "image", "images"].includes(value)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      selectVisionView();
      command.value = "";
      command.blur();
    }
  }, true);
})();
