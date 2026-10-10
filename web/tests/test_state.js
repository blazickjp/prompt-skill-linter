'use strict';
// Focused JS state-unit tests with minimal DOM stubs; not a browser test.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const nodes = new Map();
const repair = {disabled: true};
const context = {
  assert,
  document: {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, {disabled: false, textContent: ''});
      return nodes.get(id);
    },
    querySelectorAll(selector) {
      return selector === '[data-busy-lock]' ? [repair] : [];
    },
  },
  repair,
};
const source = fs.readFileSync(require('node:path').join(__dirname, '..', 'app.js'), 'utf8').replace(/\ninit\(\);\s*$/, '');
vm.createContext(context);
vm.runInContext(source + `
setBusy(true);
assert.equal(repair.disabled, true);
setBusy(false);
assert.equal(repair.disabled, false, 'dynamic repair buttons must unlock after analysis');
assert.equal(document.getElementById('source-editor').disabled, false);
assert.throws(() => parseJSON('{"n":1000000000000000001}'), /precision/);
assert.equal(parseJSON('{"n":150}').n, 150);
assert.equal(diagnosticKey({code:'x', responsible_rule_set:['b','a'], triggering_context:{x:1,y:2}}), diagnosticKey({code:'x', responsible_rule_set:['a','b'], triggering_context:{y:2,x:1}}));
assert.equal(inputChanges({runtime:{budget:30}},{runtime:{budget:32}})[0].path, '/runtime/budget');
const mixed = reportStatus({diagnostics:[{severity:'error',code:'INCOMPATIBLE_OBLIGATIONS'},{severity:'warning',code:'INCOMPLETE_SOURCE_COVERAGE'},{severity:'warning',code:'PLAN_BOUND_EXHAUSTED'}],coverage:{incomplete_reasons:['source_coverage','search_bounds']}});
assert.match(mixed, /1 error-level finding/);
assert.match(mixed, /Incomplete source coverage/);
assert.match(mixed, /result unknown/);
assert.equal(reportStatus({diagnostics:[]}), 'No error-level findings in checked inputs');
`, context);
console.log('PASS: busy-state repair unlock, safe integer parsing, canonical identities, input diffs');
