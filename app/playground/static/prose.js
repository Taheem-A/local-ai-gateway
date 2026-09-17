"use strict";

/* Shared safe prose presentation for Stage 4/5 workbench surfaces.
 *
 * API transport stays in app.js and structured/raw payloads remain available.
 * This layer only upgrades user-visible free-form model prose after a request
 * completes, using the local Markdown renderer that never interprets raw HTML.
 */

(() => {
  function mountMarkdown(target, text) {
    if (!target) return;
    const source = String(text || "");
    target.classList.remove("empty");
    if (window.PlaygroundMarkdown?.mount) {
      window.PlaygroundMarkdown.mount(target, source);
    } else {
      target.textContent = source;
    }
  }

  function renderGenerateWhenComplete() {
    const state = document.getElementById("generate-state");
    const output = document.getElementById("generate-output");
    if (!state || !output) return;
    if (state.textContent?.trim().toLowerCase() !== "completed") return;

    const source = output.dataset.rawMarkdown ?? output.textContent ?? "";
    mountMarkdown(output, source);
  }

  function renderRagAnswer() {
    const raw = document.getElementById("rag-output")?.textContent?.trim();
    const target = document.getElementById("rag-answer");
    if (!raw || !target || raw === "Waiting for a request.") return;

    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }

    if (typeof payload.answer === "string" && payload.answer.trim()) {
      target.replaceChildren();
      const prose = document.createElement("div");
      prose.className = "prose-output";
      mountMarkdown(prose, payload.answer);
      target.append(prose);
    }
  }

  function ensureToolProse() {
    const raw = document.getElementById("tools-output");
    if (!raw) return null;
    let target = document.getElementById("tools-prose");
    if (target) return target;

    target = document.createElement("div");
    target.id = "tools-prose";
    target.className = "prose-output hidden";
    raw.before(target);
    return target;
  }

  function renderToolSynthesis() {
    const raw = document.getElementById("tools-output")?.textContent?.trim();
    const target = ensureToolProse();
    if (!raw || !target || raw === "Waiting for a request.") return;

    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      target.classList.add("hidden");
      return;
    }

    const text = typeof payload.text === "string" ? payload.text.trim() : "";
    if (payload.status === "completed" && text) {
      target.classList.remove("hidden");
      mountMarkdown(target, text);
    } else {
      target.replaceChildren();
      target.classList.add("hidden");
    }
  }

  function wireSharedProse() {
    const generationState = document.getElementById("generate-state");
    if (generationState) {
      new MutationObserver(renderGenerateWhenComplete).observe(generationState, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }

    const ragOutput = document.getElementById("rag-output");
    if (ragOutput) {
      new MutationObserver(renderRagAnswer).observe(ragOutput, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }

    const toolsOutput = document.getElementById("tools-output");
    if (toolsOutput) {
      ensureToolProse();
      new MutationObserver(renderToolSynthesis).observe(toolsOutput, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
  }

  document.addEventListener("DOMContentLoaded", wireSharedProse);
})();
