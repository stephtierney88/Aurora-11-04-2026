"""Repeated complete guarded runtimes, deliberate crashes and persisted inbox replay."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from offline_panel_smoke import COPY_FILES, ROOT
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0] + '''
import json
from types import SimpleNamespace
runtime.pyautogui.position = lambda: SimpleNamespace(x=0,y=0)
runtime.process_assistant_response = lambda *args, **kwargs: None
runtime.maybe_build_episodic_planning_context = lambda *args, **kwargs: {"used":False}
runtime.AUTO_DYNAMIC_INFERENCE_ENABLED = False
runtime.REVIEW_TURN_INTERVAL = runtime.CRITIQUE_TURN_INTERVAL = 0
runtime.MODEL_TRANSPORT = "chat_completions"
fixture_mode = "success"
def fake_provider(packet,token):
    token.check()
    with Path('fake-provider-calls.jsonl').open('a') as target:
        target.write(json.dumps({'mode':fixture_mode})+'\\n')
    if fixture_mode == 'block':
        Path('provider-entered').write_text('fake request started')
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            time.sleep(.02)
        raise AssertionError('Parent failed to terminate the bounded fixture')
    return SimpleNamespace(status_code=200,json=lambda:{'model':'fixture-model','choices':[{'message':{'content':'Fixture reply'}}]}),'api_key','fixture'
runtime.perform_model_http_request = fake_provider
def controlled_turn():
    global fixture_mode
    trigger=Path('turn-trigger')
    if not trigger.exists(): return False
    fixture_mode=trigger.read_text(); trigger.unlink()
    runtime.SEND_TO_MODEL=runtime.ENABLE_MODEL_RESPONSES=True
    try: return runtime.handle_queued_input('','')
    finally: runtime.SEND_TO_MODEL=runtime.ENABLE_MODEL_RESPONSES=False
runtime.maybe_run_due_inference_turn=controlled_turn
runtime.main()
'''


def run_smoke():
    sys.path.insert(0,str(ROOT))
    import psutil
    from aurora_control_plane import append_bridge_request, append_jsonl_record, control_plane_paths, wait_for_command_receipt, journal_offsets, read_jsonl_from
    started=time.monotonic()
    checks, ownership, children = [], [], []
    process=None
    def check(name,condition):
        assert condition,name
        checks.append(name)
    with tempfile.TemporaryDirectory(dir=ROOT,prefix='.aurora-recovery-restart-') as directory:
        work=Path(directory).resolve()
        assert work.parent==ROOT.resolve()
        paths=control_plane_paths(work)
        for name in COPY_FILES: shutil.copy2(ROOT/name,work/name)
        (work/'fixture.py').write_text(FIXTURE,encoding='utf-8')
        env=dict(os.environ,AURORA_INPUT_RECOVERY='durable',AURORA_ENABLE_TEXT_INPUT_PROCESS='0',AURORA_AUTH_MODE='api_key',PYTHONUNBUFFERED='1',AURORA_PYTHON=sys.executable)
        flags=['--offline','--lock-live','--no-ui','--no-live-init','--init-mode','skip','--no-chat-log-echo','--no-smoke-test','--no-sound','--action-mode','none']
        def until(predicate,label):
            deadline=time.monotonic()+18
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise AssertionError((work/f'runtime-{len(ownership)}.log').read_text(encoding='utf-8',errors='replace')[-5000:])
                value=predicate()
                if value: return value
                time.sleep(.05)
            raise AssertionError(label)
        def state():
            try: return json.loads((work/'aurora_control_panel_state.json').read_text(encoding='utf-8-sig'))
            except (OSError,ValueError): return {}
        def command(text,success=True):
            offsets=journal_offsets(work)
            request=append_bridge_request(work,text,raw=True,client_id='restart_probe')
            receipt=wait_for_command_receipt(work,request['request_id'],client_id=request['client_id'],offsets=offsets,timeout_seconds=12)
            results=receipt.get('memory_command_results') or []
            check(text.split('(')[0]+' receipt',receipt.get('terminal') and bool(results) and results[0]['success'] is success)
            return results[0]
        def page(): return command('SHOW_INPUT_RECOVERY(0,10)')['readback']
        def launch():
            nonlocal process
            index=len(ownership)+1
            with (work/f'runtime-{index}.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,str(work/'fixture.py'),*flags],cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            ownership.append(dict(pid=process.pid,started_at_epoch=psutil.Process(process.pid).create_time(),fixture_path=str(work)))
            until(lambda:(state().get('processes',{}).get('runtime',{}).get('pid')==process.pid and state().get('modes',{}).get('input_recovery')=='durable'),'fresh runtime export')
            check('startup leaves inference paused',not state().get('modes',{}).get('live'))
        def stop(crash=False):
            if process is None or process.poll() is not None: return
            owned_children=[dict(pid=p.pid,started_at_epoch=p.create_time()) for p in psutil.Process(process.pid).children(recursive=True)]
            children.extend(owned_children)
            if crash:
                subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10,check=True)
            else:
                append_bridge_request(work,'SHUTDOWN_RUNTIME()',raw=True,client_id='restart_cleanup')
            process.wait(timeout=12)
            ownership[-1].update(exit_code=process.returncode,intentional_crash=crash)
            for child in owned_children:
                try:
                    p=psutil.Process(child['pid'])
                    if abs(p.create_time()-child['started_at_epoch'])<.01: p.wait(timeout=5)
                except psutil.NoSuchProcess: pass
        try:
            launch()
            original=append_bridge_request(work,'Restart fixture input',raw=False,client_id='restart_input')
            until(lambda:state().get('conversation_io',{}).get('queued_input_count')==1,'input admission')
            old=page()['entries'][0]
            check('first runtime durably queues input',old['phase']=='queued')
            stop(crash=True)
            launch()
            held=page()['entries'][0]
            check('full restart holds input with no replay',held['phase']=='held' and state().get('conversation_io',{}).get('queued_input_count')==0 and not (work/'fake-provider-calls.jsonl').exists())
            command(f"RETRY_INPUT({old['entry_id']},{old['version']})",False)
            command(f"RETRY_INPUT({held['entry_id']},{held['version']})")
            (work/'turn-trigger').write_text('block')
            until(lambda:(work/'provider-entered').exists(),'fake request entered')
            stop(crash=True)
            launch()
            uncertain=page()['entries'][0]
            check('request crash recovers uncertain started evidence',uncertain['phase']=='uncertain' and uncertain['request_started'] and uncertain['attempt']==2 and state().get('conversation_io',{}).get('queued_input_count')==0)
            command(f"RETRY_INPUT({uncertain['entry_id']},{uncertain['version']})",False)
            command(f"RETRY_INPUT({uncertain['entry_id']},{uncertain['version']},allow_uncertain)")
            (work/'turn-trigger').write_text('success')
            until(lambda:state().get('conversation_io',{}).get('input_recovery',{}).get('phases',{}).get('responded')==1,'response durable')
            responded=page()['entries'][0]
            check('third runtime records explicit retry response',responded['attempt']==3 and responded['identity']!=uncertain['identity'])
            preview=command('PREVIEW_INPUT_RECOVERY_COMPACTION(0,10)')['readback']
            check('preview selects exact terminal input',preview['selected_count']==1 and preview['selected'][0]['entry_id']==old['entry_id'])
            compact=command(preview['apply_command'])['after']
            check('compaction leaves dedup hash without retry payload',compact['compacted_count']==1 and page()['entries']==[])
            stop()
            # Deliberately lose only this fixture's inbox cursor. Persisted
            # admission and recovery evidence must fence old envelopes/commands.
            bridge_state=work/'aurora_external_bridge_state.json'
            assert bridge_state.parent==work
            bridge_state.unlink()
            launch()
            before=page()
            check('v2 survives full restart and cursor loss',before['total']==0 and before['compacted']==1)
            offsets=journal_offsets(work)
            append_jsonl_record(paths['inbox'],original)
            duplicate=until(lambda:next((r for r in read_jsonl_from(paths['bridge_log'],offsets['bridge_log'])[0]
                if r.get('request_id')==original['request_id'] and r.get('event')=='message_ingested'),None),'duplicate read')
            check('compacted duplicate produces explicit retained receipt',duplicate.get('delivery_status')=='recovery_retained')
            command('SHOW_INPUT_RECOVERY(0,10)')
            check('replayed compacted original cannot enqueue',state().get('conversation_io',{}).get('queued_input_count')==0)
            conflict=dict(original,text='Changed envelope payload')
            offsets=journal_offsets(work)
            append_jsonl_record(paths['inbox'],conflict)
            conflict_receipt=wait_for_command_receipt(work,original['request_id'],client_id=original['client_id'],offsets=offsets,timeout_seconds=12)
            check('same compacted identity with changed text rejected',conflict_receipt.get('event')=='command_result' and conflict_receipt.get('status')=='rejected')
            calls=[json.loads(line) for line in (work/'fake-provider-calls.jsonl').read_text().splitlines()]
            check('only the two explicitly triggered fake calls occurred',calls==[{'mode':'block'},{'mode':'success'}])
            check('no native guard touched',not (work/'forbidden-native-input.txt').exists())
            stop()
        finally:
            if process is not None and process.poll() is None:
                stop(crash=True)
        proof=dict(status='passed',checks=checks,check_count=len(checks),runtime_starts=len(ownership),
                   real_api_calls=0,native_calls=0,fake_provider_calls=2,ownership=ownership,owned_children=children,
                   elapsed_seconds=round(time.monotonic()-started,3))
    proof['fixture_removed']=not work.exists()
    return proof


if __name__=='__main__': print(json.dumps(run_smoke(),indent=2))
