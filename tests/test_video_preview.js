const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('partyforge/static/app.js', 'utf8');
const start = source.indexOf('document.querySelectorAll("[data-video-preview]")');
const end = source.indexOf('document.querySelectorAll("[data-push-panel]")', start);
const classes = new Set();
const handlers = {};
const status = {hidden: false};
const frame = {contentWindow: {}, addEventListener: (name, fn) => {handlers[name] = fn;}};
const card = {
  querySelector: selector => selector === 'iframe' ? frame : status,
  classList: {add: name => classes.add(name), remove: name => classes.delete(name)}
};
vm.runInNewContext(source.slice(start, end), {
  document: {querySelectorAll: () => [card]},
  window: {addEventListener: (name, fn) => {handlers[name] = fn;}, setTimeout: fn => {handlers.timeout = fn;}}
});
handlers.timeout();
assert(classes.has('preview-unavailable'));
handlers.load();
assert.equal(status.hidden, true);
assert(!classes.has('preview-unavailable'));
handlers.timeout();
assert(!classes.has('preview-unavailable'), 'A loaded player must stay visible after timeout');
const error = {source: frame.contentWindow, origin:'https://evil.example', data:{'x-tiktok-player':true,type:'onPlayerError'}};
handlers.message(error);
assert(!classes.has('preview-unavailable'));
handlers.message({...error,origin:'https://www.tiktok.com'});
assert(classes.has('preview-unavailable'));
handlers.message({...error,origin:'https://www.tiktok.com',data:{'x-tiktok-player':true,type:'onPlayerReady'}});
assert(!classes.has('preview-unavailable'));
console.log('video preview tests passed');
