"use strict";

/* Safe, dependency-free Markdown rendering for model prose.
 *
 * The renderer deliberately supports only the subset the playground needs:
 * headings, paragraphs, unordered/ordered lists, block quotes, fenced code,
 * inline code, emphasis, strong text, and http(s) links. Raw HTML is never
 * interpreted; all user/model text enters the DOM through text nodes.
 */

(() => {
  function appendInline(target, source) {
    const tokenPattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;
    let index = 0;
    for (const match of source.matchAll(tokenPattern)) {
      const start = match.index ?? 0;
      if (start > index) target.append(document.createTextNode(source.slice(index, start)));
      const token = match[0];
      if (token.startsWith("**")) {
        const strong = document.createElement("strong");
        strong.textContent = token.slice(2, -2);
        target.append(strong);
      } else if (token.startsWith("`") && token.endsWith("`")) {
        const code = document.createElement("code");
        code.textContent = token.slice(1, -1);
        target.append(code);
      } else if (token.startsWith("*") && token.endsWith("*")) {
        const em = document.createElement("em");
        em.textContent = token.slice(1, -1);
        target.append(em);
      } else if (token.startsWith("[")) {
        const split = token.indexOf("](");
        const href = token.slice(split + 2, -1);
        const anchor = document.createElement("a");
        anchor.textContent = token.slice(1, split);
        anchor.href = href;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        target.append(anchor);
      } else {
        target.append(document.createTextNode(token));
      }
      index = start + token.length;
    }
    if (index < source.length) target.append(document.createTextNode(source.slice(index)));
  }

  function render(markdown) {
    const fragment = document.createDocumentFragment();
    const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    let paragraph = [];
    let list = null;
    let code = null;

    function flushParagraph() {
      if (!paragraph.length) return;
      const p = document.createElement("p");
      appendInline(p, paragraph.join(" ").trim());
      fragment.append(p);
      paragraph = [];
    }

    function flushList() {
      if (!list) return;
      fragment.append(list);
      list = null;
    }

    function flushCode() {
      if (!code) return;
      const pre = document.createElement("pre");
      const node = document.createElement("code");
      if (code.language) node.dataset.language = code.language;
      node.textContent = code.lines.join("\n");
      pre.append(node);
      fragment.append(pre);
      code = null;
    }

    for (const line of lines) {
      const fence = line.match(/^```\s*([\w.+-]*)\s*$/);
      if (fence) {
        flushParagraph();
        flushList();
        if (code) flushCode();
        else code = { language: fence[1] || "", lines: [] };
        continue;
      }
      if (code) {
        code.lines.push(line);
        continue;
      }
      if (!line.trim()) {
        flushParagraph();
        flushList();
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        flushList();
        const h = document.createElement(`h${heading[1].length}`);
        appendInline(h, heading[2]);
        fragment.append(h);
        continue;
      }
      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        const blockquote = document.createElement("blockquote");
        appendInline(blockquote, quote[1]);
        fragment.append(blockquote);
        continue;
      }
      const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (unordered || ordered) {
        flushParagraph();
        const tag = ordered ? "ol" : "ul";
        if (!list || list.tagName.toLowerCase() !== tag) {
          flushList();
          list = document.createElement(tag);
        }
        const item = document.createElement("li");
        appendInline(item, (unordered || ordered)[1]);
        list.append(item);
        continue;
      }
      flushList();
      paragraph.push(line.trim());
    }

    flushParagraph();
    flushList();
    flushCode();
    return fragment;
  }

  function mount(target, source) {
    target.replaceChildren(render(source));
    target.dataset.markdownRendered = "true";
    target.dataset.rawMarkdown = source || "";
  }

  function raw(target) {
    return target.dataset.rawMarkdown ?? target.textContent ?? "";
  }

  window.PlaygroundMarkdown = { render, mount, raw };
})();
