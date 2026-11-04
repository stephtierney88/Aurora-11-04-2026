// Exercise the shipped browser script against a small DOM/API fixture, no browser or native capture.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
class Element {
  constructor() { this.value = ''; this.textContent = ''; this.children = []; this.hidden = false; this.disabled = false; this.listeners = {}; this.classList = {add(){}, remove(){}}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(event, fn) { this.listeners[event] = fn; }
}
const html = fs.readFileSync(path.join(root, 'aurora_validation_web/index.html'), 'utf8');
const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
const preset = {name:'Effort',case:'effort',transport:'responses',model:'gpt-6-astra',alternate_model:'gpt-5.2',baseline_effort:'low',changed_effort:'high',prompt:'Fixture',timeout_seconds:45,max_calls:3};
const commands = [{command:'SET_NEXT_REASONING_EFFORT',summary:'Queued effort',handler:'effort',aliases:['EFFORT_ALIAS'],subsystems:['Adaptive reasoning'],contract:{parameter_validation:'pre_dispatch'}}, {command:'OTHER',summary:'Other capability',handler:'other',aliases:[],subsystems:['Other capabilities'],contract:{parameter_validation:'legacy'}}];
let profiles = [], runs = [];
const requests = [];
const context = {console, URLSearchParams, location:{hash:'#token=test'}, history:{replaceState(){}}, sessionStorage:{setItem(){},getItem(){return null;}},
  document:{hidden:false,getElementById:id=>elements[id]||null,createElement:()=>new Element(),addEventListener(){}},
  crypto:{randomUUID:()=> 'run-fixture'}, setInterval(){}, setTimeout, Blob, URL,
  fetch:async (url, options) => {
    assert.equal(options.headers.Authorization, 'Bearer test');
    requests.push(url);
    const body = options.body ? JSON.parse(options.body) : null;
    let value;
    if(url==='/api/catalog') value = {catalog:{commands},source:{fingerprint:'local'},presets:{effort:preset},fixture_matrix:{models:['gpt-6-astra','gpt-5.2'],efforts:['low','high']}};
    if(url==='/api/profiles') {if(body) profiles.push({version:'v1',profile:body.profile}); value = body ? profiles.at(-1) : profiles;}
    if(url==='/api/preview') value = {mode:'dry_run',profile:body.profile,real_api_calls:0};
    if(url==='/api/run') {runs=[{run_id:body.request_id,profile:body.profile,status:'passed',started_at:1,real_api_calls:0,result:{restoration_verified:true,turns:[{phase:'baseline',model:'gpt-6-astra',sent_effort:'low',controller_effort:'low',elapsed_ms:2}]}}]; value=runs[0];}
    if(url==='/api/runs') value = runs;
    return {ok:true,json:async()=>value};
  }};
vm.runInNewContext(fs.readFileSync(path.join(root, 'aurora_validation_web/app.js'),'utf8'), context);
(async()=>{
  await new Promise(setImmediate);
  assert.equal(elements.commands.children.length, 2);
  elements.query.value='effort_alias'; elements.query.listeners.input();
  assert.equal(elements.commands.children.length, 1);
  elements.commands.children[0].onclick(); assert.equal(elements.detail.children[0].textContent,'SET_NEXT_REASONING_EFFORT');
  elements.validateTab.onclick(); assert.equal(elements.browser.hidden,true);
  elements.name.value='Saved edit'; await elements.save.onclick(); assert.equal(profiles[0].profile.name,'Saved edit');
  elements.prompt.value='Changed input'; await elements.preview.onclick(); assert.match(elements.evidence.textContent,/Changed input/);
  assert.equal(requests.filter(r=>r==='/api/run').length,0);
  await elements.run.onclick(); assert.match(elements.runStatus.textContent,/passed/); assert.equal(elements.turns.children.length,1);
  assert.equal(elements.error.textContent,'');
  console.log('Web DOM/API smoke passed: catalog/alias filter, details, navigation, save, preview and results. Visual layout untested.');
})().catch(error=>{console.error(error);process.exitCode=1;});
