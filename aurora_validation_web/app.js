'use strict';
const $ = id => document.getElementById(id);
let token = new URLSearchParams(location.hash.slice(1)).get('token');
if (token) { sessionStorage.setItem('aurora-validation-token', token); history.replaceState(null, '', '/'); }
token = token || sessionStorage.getItem('aurora-validation-token') || '';
let data, currentCase = 'effort', activeRun = null, shown = null, saved = [], runningRequest = null;
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body ? 'POST' : 'GET',
    headers: {'Authorization': 'Bearer ' + token, ...(body ? {'Content-Type': 'application/json'} : {})},
    ...(body ? {body: JSON.stringify(body)} : {})});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Local request failed');
  return value;
}
function error(e) { $('error').textContent = e.message; $('error').hidden = false; }
function guarded(fn) { return async () => { $('error').hidden = true; try { await fn(); } catch (e) { error(e); } }; }
function option(select, value, label = value) { const item = document.createElement('option'); item.value = value; item.textContent = label; select.append(item); }
function fill(profile) { currentCase = profile.case; $('preset').value = currentCase; Object.keys(profile).filter(k => $(k)).forEach(k => $(k).value = profile[k]); }
function profile() { const value = {...data.presets[currentCase]}; Object.keys(value).filter(k => $(k)).forEach(k => value[k] = $(k).value); value.timeout_seconds = Number(value.timeout_seconds); return value; }
function showEvidence(value) { shown = value; $('evidence').textContent = JSON.stringify(value, null, 2); $('export').disabled = false; }
function renderCommands() {
  const q = $('query').value.toLowerCase(), subsystem = $('subsystem').value, coverage = $('coverage').value;
  const rows = data.catalog.commands.filter(row => (!subsystem || row.subsystems.includes(subsystem)) &&
    (!coverage || (coverage === 'pre_dispatch') === (row.contract.parameter_validation === 'pre_dispatch')) &&
    [row.command, row.summary, row.handler, ...row.aliases].join(' ').toLowerCase().includes(q));
  $('count').textContent = `${rows.length} of ${data.catalog.commands.length} bindings · all aliases retained`;
  $('commands').replaceChildren();
  rows.forEach(row => { const button = document.createElement('button'); button.className = 'command'; button.textContent = row.command;
    const small = document.createElement('small'); small.textContent = row.subsystems.join(' · '); button.append(small);
    button.onclick = () => { $('detail').replaceChildren(); const title = document.createElement('h2'); title.textContent = row.command;
      const summary = document.createElement('p'); summary.textContent = row.summary; const pre = document.createElement('pre'); pre.textContent = JSON.stringify(row, null, 2); $('detail').append(title, summary, pre); };
    $('commands').append(button); });
}
async function profiles() { saved = await api('profiles'); $('saved').replaceChildren(); option($('saved'), '', 'Choose a saved version'); saved.forEach((row, i) => option($('saved'), String(i), row.profile.name + ' · ' + row.version.slice(0, 8))); }
function displayRun(row) {
  showEvidence(row); $('runStatus').textContent = `${row.status} · ${row.profile.name} · restoration ${row.result?.restoration_verified ?? 'unknown'} · API calls ${row.real_api_calls}`;
  $('turns').replaceChildren(); (row.result?.turns || []).forEach(turn => { const tr = document.createElement('tr');
    [turn.phase, turn.model, turn.sent_effort, turn.controller_effort, turn.elapsed_ms].forEach(value => { const td = document.createElement('td'); td.textContent = value ?? 'unknown'; tr.append(td); }); $('turns').append(tr); });
}
async function refreshRuns() {
  const rows = await api('runs'); $('runs').replaceChildren();
  rows.forEach(row => { const button = document.createElement('button'); button.textContent = `${row.profile.name} · ${row.status} · ${new Date(row.started_at * 1000).toLocaleString()}`; button.onclick = () => displayRun(row); $('runs').append(button); });
  const active = rows.find(row => row.status === 'running' || row.status === 'cancelling'); activeRun = active?.run_id || null;
  $('run').disabled = !!activeRun; $('cancel').disabled = !activeRun;
  if (active) displayRun(active); else if (runningRequest) { const finished = rows.find(row => row.run_id === runningRequest); if (finished) { displayRun(finished); runningRequest = null; } }
}
$('browseTab').onclick = () => { $('browser').hidden = false; $('validation').hidden = true; $('browseTab').classList.add('selected'); $('validateTab').classList.remove('selected'); };
$('validateTab').onclick = () => { $('browser').hidden = true; $('validation').hidden = false; $('validateTab').classList.add('selected'); $('browseTab').classList.remove('selected'); };
['query', 'subsystem', 'coverage'].forEach(id => $(id).addEventListener('input', renderCommands));
$('preset').onchange = () => fill(data.presets[$('preset').value]);
$('saved').onchange = () => { if ($('saved').value !== '') fill(saved[Number($('saved').value)].profile); };
$('save').onclick = guarded(async () => { const row = await api('profiles', {profile: profile()}); await profiles(); showEvidence(row); });
$('preview').onclick = guarded(async () => { showEvidence(await api('preview', {profile: profile(), fingerprint: data.source.fingerprint})); $('runStatus').textContent = 'Dry-run validated · no runtime started'; $('turns').replaceChildren(); });
$('run').onclick = guarded(async () => { $('run').disabled = true; const requestId = crypto.randomUUID(); try { const row = await api('run', {profile: profile(), fingerprint: data.source.fingerprint, request_id: requestId}); runningRequest = row.run_id; displayRun(row); await refreshRuns(); } finally { $('run').disabled = !!activeRun; } });
$('cancel').onclick = guarded(async () => { if (activeRun) await api('cancel', {run_id: activeRun}); await refreshRuns(); });
$('export').onclick = () => { const url = URL.createObjectURL(new Blob([JSON.stringify(shown, null, 2)], {type:'application/json'})); const a = document.createElement('a'); a.href = url; a.download = 'aurora-offline-evidence.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
guarded(async () => {
  data = await api('catalog'); $('provenance').textContent = JSON.stringify({local_head:data.local_head, local_dirty:data.local_dirty, source_fingerprint:data.source.fingerprint, connected_repository:data.connected_repository, existing_runtime:data.existing_runtime}, null, 2);
  [...new Set(data.catalog.commands.flatMap(row => row.subsystems))].sort().forEach(s => option($('subsystem'), s));
  Object.entries(data.presets).forEach(([key, row]) => option($('preset'), key, row.name));
  ['model', 'alternate_model'].forEach(id => data.fixture_matrix.models.forEach(m => option($(id), m)));
  ['baseline_effort', 'changed_effort'].forEach(id => data.fixture_matrix.efforts.forEach(e => option($(id), e)));
  fill(data.presets.effort); renderCommands(); await profiles(); await refreshRuns();
  setInterval(() => { if (activeRun && !document.hidden) refreshRuns().catch(error); }, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshRuns().catch(error); });
})();
