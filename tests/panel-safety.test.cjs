const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('nexora/static/panel-safety.js', 'utf8');

function setup() {
  const handlers = {}, windowHandlers = {};
  const attrs = {};
  const button = {dataset: {}, setAttribute(k,v) {attrs[k]=v;}, removeAttribute(k) {delete attrs[k];}};
  const form = {method: 'post', dataset: {}, addEventListener(k,v) {handlers[k]=v;},
    setAttribute(k,v) {attrs[k]=v;}, removeAttribute(k) {delete attrs[k];},
    querySelectorAll() {return [button];}};
  const notice = {textContent: ''};
  let reloads=0, confirm=true, tick;
  const document = {body: {dataset: {section: 'solicitudes'}}, hidden:false,
    activeElement: {matches:()=>false}, getElementById:()=>notice, querySelectorAll:()=>[form]};
  const window = {confirm:()=>confirm, location:{reload:()=>reloads++},
    setInterval:fn=>{tick=fn;}, addEventListener:(k,v)=>{windowHandlers[k]=v;}};
  vm.runInNewContext(source, {document, window});
  const submit = () => {
    const event={defaultPrevented:false, submitter:button, preventDefault(){this.defaultPrevented=true;}};
    handlers.submit(event); return event;
  };
  return {handlers, windowHandlers, document, button, notice, attrs, submit,
    tick:()=>tick(), reloads:()=>reloads, reject:()=>{confirm=false;}};
}
test('idle refreshes but typing and pending submissions do not',()=>{
  const s=setup(); s.tick(); assert.equal(s.reloads(),1);
  s.handlers.input(); s.tick(); assert.equal(s.reloads(),1);
  assert.match(s.notice.textContent,/pausada/);
  s.submit(); s.tick(); assert.equal(s.reloads(),1);
});
test('double submit blocked without disabling action name/value',()=>{
  const s=setup(); assert.equal(s.submit().defaultPrevented,false);
  assert.equal(s.submit().defaultPrevented,true);
  assert.equal(s.button.disabled,undefined);
  assert.equal(s.attrs['aria-busy'],'true');
});
test('cancelled confirmation does not lock the form',()=>{
  const s=setup(); s.button.dataset.confirm='Confirmar'; s.reject();
  assert.equal(s.submit().defaultPrevented,true);
  assert.equal(s.attrs['aria-busy'],undefined);
});
test('restoring page permits a deliberate new submit',()=>{
  const s=setup(); s.submit(); s.windowHandlers.pageshow();
  assert.equal(s.attrs['aria-busy'],undefined);
  assert.equal(s.submit().defaultPrevented,false);
});
test('hidden or focused page does not reload',()=>{
  const s=setup(); s.document.hidden=true; s.tick(); assert.equal(s.reloads(),0);
  s.document.hidden=false; s.document.activeElement.matches=()=>true;
  s.tick(); assert.equal(s.reloads(),0);
});
test('unsent edits warn on navigation',()=>{
  const s=setup(); s.handlers.input();
  let prevented=false; const event={preventDefault(){prevented=true;}};
  s.windowHandlers.beforeunload(event); assert.equal(prevented,true);
  s.submit(); prevented=false; s.windowHandlers.beforeunload(event);
  assert.equal(prevented,false);
});
