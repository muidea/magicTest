const { test } = require('node:test');
const assert = require('node:assert/strict');
const { observedAppearanceMatches } = require('./page_appearance_cases.cjs');
test('appearance observation rejects missing consumers, lost inheritance and boundary drift', () => {
  const value = { background: 'rgb(238, 238, 238)', visible: true, frames: [
    { key: 'appearance-inherit', color: 'rgb(17, 34, 51)', border: '12px', text: 'appearance-inherit' },
    { key: 'appearance-clear', color: 'rgba(0, 0, 0, 0)', border: '0px', text: 'appearance-clear' },
    { key: 'appearance-alpha', color: 'rgba(68, 85, 102, 0.5)', border: '12px', text: 'appearance-alpha' },
  ] };
  assert.equal(observedAppearanceMatches(value), true);
  for (const change of [v => { v.visible = false; }, v => { v.background = 'transparent'; }, v => v.frames.pop(),
    v => v.frames.push(v.frames[0]), v => { v.frames[0].color = 'rgba(0, 0, 0, 0)'; },
    v => { v.frames[1].border = '12px'; }, v => { v.frames[2].color = 'rgb(68, 85, 102)'; },
    v => { v.frames[0].text = 'other instance'; }, v => { v.frames[0].count = 2; }]) {
    const changed = structuredClone(value); change(changed); assert.equal(observedAppearanceMatches(changed), false);
  }
});
