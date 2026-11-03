(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.PartyForgeThemeParser = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function stripOuterFence(value) {
    return value.trim()
      .replace(/^```(?:json)?\s*/i, "")
      .replace(/\s*```$/, "");
  }

  function normalizeTheme(parsed) {
    return {
      css: typeof parsed.css === "string" ? parsed.css : "",
      html_top: typeof parsed.html_top === "string" ? parsed.html_top : "",
      html_bottom: typeof parsed.html_bottom === "string" ? parsed.html_bottom : ""
    };
  }

  function tryStrictJSON(value) {
    const candidates = [stripOuterFence(value)];
    const firstBrace = value.indexOf("{");
    const lastBrace = value.lastIndexOf("}");
    if (firstBrace >= 0 && lastBrace > firstBrace) candidates.push(value.slice(firstBrace, lastBrace + 1));
    for (const candidate of candidates) {
      try {
        const parsed = JSON.parse(candidate);
        if (parsed && typeof parsed === "object" && ("css" in parsed || "html_top" in parsed || "html_bottom" in parsed)) {
          return normalizeTheme(parsed);
        }
      } catch (_) {}
    }
    return null;
  }

  function decodeLooseString(value) {
    const withEscapedLines = value.replace(/\r/g, "").replace(/\n/g, "\\n");
    try {
      return JSON.parse(`"${withEscapedLines}"`);
    } catch (_) {
      return value
        .replace(/\\r\\n/g, "\n")
        .replace(/\\n/g, "\n")
        .replace(/\\t/g, "\t")
        .replace(/\\"/g, "\"")
        .replace(/\\\\/g, "\\");
    }
  }

  function tryLooseJSON(value) {
    const css = value.match(/["']css["']\s*:\s*["']([\s\S]*?)["']\s*,\s*["']html_top["']\s*:/i);
    const top = value.match(/["']html_top["']\s*:\s*["']([\s\S]*?)["']\s*,\s*["']html_bottom["']\s*:/i);
    const bottom = value.match(/["']html_bottom["']\s*:\s*["']([\s\S]*?)["']\s*}\s*(?:```)?\s*$/i);
    if (!css || !top || !bottom) return null;
    return {
      css: decodeLooseString(css[1]),
      html_top: decodeLooseString(top[1]),
      html_bottom: decodeLooseString(bottom[1])
    };
  }

  function headingKey(label) {
    const normalized = label.toUpperCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
    if (normalized === "CSS" || normalized === "CUSTOM CSS") return "css";
    if (/^(?:HTML )?(?:TOP|ABOVE)$/.test(normalized) || /^(?:TOP|ABOVE) HTML$/.test(normalized) || normalized.includes("HTML ABOVE")) return "html_top";
    if (/^(?:HTML )?(?:BOTTOM|BELOW)$/.test(normalized) || /^(?:BOTTOM|BELOW) HTML$/.test(normalized) || normalized.includes("HTML BELOW")) return "html_bottom";
    return null;
  }

  function trySections(value) {
    const heading = /(?:^|\n)\s*(?:={2,}|#{1,4})\s*([^\n=]+?)\s*(?:={2,})?\s*\n/g;
    const matches = [...value.matchAll(heading)];
    const result = {css: "", html_top: "", html_bottom: ""};
    let recognized = 0;
    matches.forEach((match, index) => {
      const key = headingKey(match[1]);
      if (!key) return;
      const start = match.index + match[0].length;
      const end = index + 1 < matches.length ? matches[index + 1].index : value.length;
      result[key] = value.slice(start, end).trim()
        .replace(/^```(?:css|html)?\s*/i, "")
        .replace(/\s*```$/, "");
      recognized += 1;
    });
    return recognized >= 2 && result.css ? result : null;
  }

  function tryFences(value) {
    const blocks = [...value.matchAll(/```\s*(css|html)?\s*\n?([\s\S]*?)```/gi)];
    if (blocks.length < 3) return null;
    const cssIndex = blocks.findIndex((block) => (block[1] || "").toLowerCase() === "css");
    const cssBlock = cssIndex >= 0 ? blocks[cssIndex] : blocks[0];
    const htmlBlocks = blocks.filter((_, index) => index !== (cssIndex >= 0 ? cssIndex : 0));
    return {css: cssBlock[2].trim(), html_top: htmlBlocks[0][2].trim(), html_bottom: htmlBlocks[1][2].trim()};
  }

  function parseThemeResponse(value) {
    const input = String(value || "").trim();
    if (!input) throw new Error("Paste the AI response first.");
    const parsed = tryStrictJSON(input) || tryLooseJSON(input) || trySections(input) || tryFences(input);
    if (!parsed || !parsed.css) throw new Error("No recognizable CSS/HTML theme sections found.");
    return normalizeTheme(parsed);
  }

  return {parseThemeResponse};
});
