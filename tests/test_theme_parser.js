const assert = require("node:assert/strict");
const {parseThemeResponse} = require("../partyforge/static/theme-parser.js");

const strict = parseThemeResponse(JSON.stringify({
  css: "body { color: red; }",
  html_top: '<div class="top">Top</div>',
  html_bottom: "<div>Bottom</div>"
}));
assert.equal(strict.css, "body { color: red; }");

const brokenMultilineJSON = parseThemeResponse(`{
  "css":"body {
    color: blue;
  }",
  "html_top":"<div class="bubbles">Top</div>",
  "html_bottom":"<div>Bottom</div>"
}`);
assert.match(brokenMultilineJSON.css, /color: blue/);
assert.match(brokenMultilineJSON.html_top, /class="bubbles"/);

const labeled = parseThemeResponse(`Here is your theme:
=== CSS ===
\`\`\`css
.invite { border-radius: 2rem; }
\`\`\`
=== HTML TOP ===
\`\`\`html
<div class="stars">Stars</div>
\`\`\`
=== HTML BOTTOM ===
\`\`\`html
<div class="waves">Waves</div>
\`\`\``);
assert.match(labeled.css, /border-radius/);
assert.match(labeled.html_bottom, /waves/);

const fencesOnly = parseThemeResponse(`
\`\`\`css
body { background: orange; }
\`\`\`
\`\`\`html
<div>Above</div>
\`\`\`
\`\`\`html
<div>Below</div>
\`\`\``);
assert.match(fencesOnly.css, /orange/);
assert.match(fencesOnly.html_top, /Above/);

console.log("theme parser tests passed");
