"""Hidden real Tk -> inbox -> production recovery commands; no native input/API."""
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


def check_panel(work):
    sys.path.insert(0,str(work))
    os.chdir(work)
    import aurora2_control_panel as panel
    from aurora_control_plane import append_bridge_request, read_jsonl_from
    panel.save_layout_preferences(panel.LAYOUT_PATH, {'maximized':False})
    panel.write_pid_file(panel.CONTROL_PANEL_PID_PATH, os.getpid())
    app = panel.AuroraControlPanel()
    app.withdraw()
    errors, checks = [], []
    app.report_callback_exception = lambda kind,value,trace: errors.append(f'{kind.__name__}: {value}')
    def check(name,condition):
        assert condition,name
        checks.append(name)
    def pump():
        app.update()
        assert not errors,errors
        time.sleep(.02)
    def until(predicate,label):
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            pump()
            if predicate(): return
        raise AssertionError(label)
    def raw(command):
        record=app.send_raw(command)
        def receipt():
            rows,_=read_jsonl_from(panel.CMD_LOG_PATH)
            return next((r for r in reversed(rows) if r.get('request_id')==record['request_id'] and r.get('event')=='command_result'),None)
        until(receipt,command)
        return receipt()
    try:
        until(lambda:(app.state_cache.get('modes') or {}).get('input_recovery')=='durable','durable startup')
        outbox=app.open_conversation_outbox(); outbox.withdraw()
        recovery=outbox.recovery
        outbox.tabs.select(recovery)
        until(lambda:recovery.valid,'automatic read on recovery tab')
        check('separate session view retained', len(outbox.tabs.tabs())==2 and not app.conversation_outbox.rows)
        check('first page bounded with omitted counts',len(recovery.rows)==10 and recovery.page['total']==13 and recovery.page['omitted']==3)
        held=next(r for r in recovery.rows.values() if r['text']=='held fixture')
        uncertain=next(r for r in recovery.rows.values() if r['text']=='uncertain fixture')
        responded=next(r for r in recovery.rows.values() if r['text']=='responded fixture')
        check('readiness shows startup source and uncertain count', 'AURORA_INPUT_RECOVERY' in recovery.summary.get()
              and 'uncertain 1' in recovery.summary.get() and 'unacknowledged' in recovery.summary.get())
        recovery.tree.selection_set(uncertain['entry_id']); recovery.select()
        check('diagnostic acknowledgement is separate from retry acknowledgement', not recovery.ack_diagnostic.instate(['disabled'])
              and not recovery.acknowledge.get() and recovery.retry.instate(['disabled']))
        before = (work/'aurora_input_recovery.json').read_bytes()
        recovery.ack_diagnostic.invoke()
        until(lambda:not recovery.client.pending, 'diagnostic acknowledgement receipt')
        check('diagnostic acknowledgement has exact confirmed receipt', 'Confirmed ACK_INPUT_RECOVERY_DIAGNOSTIC' in recovery.status.get())
        until(lambda:bool((recovery.readiness().get('diagnostic') or {}).get('acknowledged')), 'acknowledgement export')
        recovery.update_controls()
        check('diagnostic seen preserves store and retry safeguard', recovery.ack_diagnostic.instate(['disabled'])
              and '(seen)' in recovery.summary.get() and not recovery.acknowledge.get()
              and (work/'aurora_input_recovery.json').read_bytes()==before)
        recovery.load(); until(lambda:recovery.valid, 'refresh after diagnostic acknowledgement')
        recovery.tree.selection_set(held['entry_id']); recovery.select()
        check('full text and identity inspectable','held fixture' in recovery.details.get('1.0','end') and held['identity']['request_id'] in recovery.details.get('1.0','end'))
        recovery.retry.invoke()
        until(lambda:not recovery.client.pending,'held retry receipt')
        check('retry confirmed but page invalidated','Confirmed RETRY_INPUT' in recovery.status.get() and not recovery.valid)
        recovery.load(); until(lambda:recovery.valid,'retry readback')
        retry=recovery.rows[held['entry_id']]
        check('fresh identity original retained',retry['attempt']==2 and retry['identity']!=held['identity'] and retry['original_identity']==held['original_identity'] and retry['phase']=='queued')
        check('queued retry disabled',recovery.retry.instate(['disabled']))
        recovery.cancel.invoke(); until(lambda:not recovery.client.pending,'cancel queued retry')
        recovery.load(); until(lambda:recovery.valid,'cancel readback')
        check('queued cancellation confirmed',recovery.rows[held['entry_id']]['phase']=='cancelled')
        # Change the runtime behind a displayed version; UI must show conflict.
        stale=recovery.rows[held['entry_id']]
        raw(f"RETRY_INPUT({stale['entry_id']},{stale['version']})")
        recovery.retry.invoke(); until(lambda:not recovery.client.pending,'stale UI action')
        check('stale action rejected without replay','changed/reloaded' in recovery.status.get() and not recovery.valid)
        recovery.load(); until(lambda:recovery.valid,'fresh after conflict')
        recovery.cancel.invoke(); until(lambda:not recovery.client.pending,'cancel after conflict')
        recovery.load(); until(lambda:recovery.valid,'cancel after conflict readback')
        recovery.tree.selection_set(uncertain['entry_id']); recovery.select()
        check('uncertain retry requires explicit acknowledgement',recovery.retry.instate(['disabled']) and not recovery.ack.instate(['disabled']))
        recovery.ack.invoke()
        check('ack enables uncertain retry',not recovery.retry.instate(['disabled']))
        recovery.tree.selection_set(held['entry_id']); recovery.select()
        recovery.tree.selection_set(uncertain['entry_id']); recovery.select()
        check('selection change clears acknowledgement',not recovery.acknowledge.get() and recovery.retry.instate(['disabled']))
        recovery.ack.invoke(); recovery.retry.invoke()
        until(lambda:not recovery.client.pending,'acknowledged uncertain retry')
        check('uncertain retry reaches shared runtime','Confirmed RETRY_INPUT' in recovery.status.get())
        recovery.load(); until(lambda:recovery.valid,'uncertain retry readback')
        check('prior uncertainty has new attempt',recovery.rows[uncertain['entry_id']]['attempt']==2 and not recovery.rows[uncertain['entry_id']]['request_started'])
        recovery.cancel.invoke(); until(lambda:not recovery.client.pending,'cancel uncertain retry')
        recovery.load(); until(lambda:recovery.valid,'final current page')
        recovery.tree.selection_set(responded['entry_id']); recovery.select()
        check('responded records cannot retry or cancel',recovery.retry.instate(['disabled']) and recovery.cancel.instate(['disabled']))
        recovery.next.invoke(); until(lambda:recovery.valid and recovery.offset==10,'second page')
        check('second page boundaries',len(recovery.rows)==3 and recovery.page['omitted_before']==10 and recovery.next.instate(['disabled']))
        recovery.previous.invoke(); until(lambda:recovery.valid and recovery.offset==0,'previous page')
        # Test actual navigation without displaying the withdrawn fixture.
        deiconify=app.deiconify
        app.deiconify=lambda:None
        before=dict(app.switchboard.observed)
        recovery.settings()
        app.deiconify=deiconify
        check('settings link reveals the existing switch without mutation',app._get_active_tab_name()=='The Switchboard' and app.switchboard.controls.expanded and app.switchboard.observed==before)
        original=app._get_control_panel_settings_snapshot
        app._get_control_panel_settings_snapshot=lambda:({'runtime':{'running':True},'state':{'age_seconds':30}}, {})
        recovery.update_controls()
        check('stale state invalidates snapshot and actions',not recovery.valid and recovery.cancel.instate(['disabled']) and recovery.reload.instate(['disabled']))
        check('stale status and diagnostic controls disabled', recovery.refresh_status.instate(['disabled'])
              and recovery.ack_diagnostic.instate(['disabled']) and 'Historical export' in recovery.summary.get())
        app._get_control_panel_settings_snapshot=original
        recovery.load(); until(lambda:recovery.valid,'fresh state again')
        oldwindow=outbox
        check('close and reopen reuses Outbox',app.open_conversation_outbox() is oldwindow)
        outbox.withdraw()
        preview=raw('PREVIEW_INPUT_RECOVERY_COMPACTION(0,10)')['memory_command_results'][0]['readback']
        raw(preview['apply_command'])
        recovery.load(); until(lambda:recovery.valid,'compacted readback')
        check('compacted count is visible with duplicate protection label',recovery.page['compacted']==preview['selected_count'] and 'duplicate protection retained' in recovery.summary.get())
        raw('SET_INPUT_RECOVERY(legacy)')
        until(lambda:(app.state_cache.get('modes') or {}).get('input_recovery')=='legacy','legacy restored')
        recovery.update_controls()
        check('legacy remains available without erasing recovery',recovery.reload.instate(['disabled']) and not recovery.valid and (work/'aurora_input_recovery.json').exists())
        recovery.refresh_status.invoke(); until(lambda:not recovery.client.pending, 'legacy readiness receipt')
        check('status works in legacy without opening durable records', 'Confirmed SHOW_INPUT_RECOVERY_STATUS' in recovery.status.get()
              and 'Effective recovery: legacy' in recovery.status.get())
        raw('SET_INPUT_RECOVERY(durable)')
        until(lambda:(app.state_cache.get('modes') or {}).get('input_recovery')=='durable','durable restored')
        recovery.load()
        check('receipt poll scheduled',recovery._after is not None)
        outbox.destroy()
        check('destroy removes owned Tk callback',recovery._after is None)
        check('no native guard touched',not (work/'forbidden-native-input.txt').exists())
        (work/'proof.json').write_text(json.dumps(dict(status='passed',checks=checks,check_count=len(checks),real_api_calls=0,native_calls=0,displayed_layout_qualified=False),indent=2),encoding='utf-8')
    finally:
        app.on_close()


def run_smoke():
    sys.path.insert(0,str(ROOT))
    from aurora_input_recovery import InputRecovery
    from aurora_control_plane import append_bridge_request
    started=time.monotonic()
    ownership=[]
    with tempfile.TemporaryDirectory(dir=ROOT,prefix='.aurora-recovery-panel-') as directory:
        work=Path(directory).resolve()
        assert work.parent==ROOT.resolve()
        for name in COPY_FILES: shutil.copy2(ROOT/name,work/name)
        store=InputRecovery(work/'aurora_input_recovery.json')
        for index in range(13):
            identity=dict(client_id='fixture-client',request_id=f'input-{index}',message_id=f'message-{index}')
            store.admit(['held fixture','uncertain fixture','responded fixture'][index] if index<3 else f'extra fixture {index}',identity)
            if index in (1,2):
                store.claim([identity]); store.delivery([identity],'submitted',f'turn-{index}',1,True)
                if index==2: store.delivery([identity],'responded',f'turn-{index}',2,True)
        store.close()
        fixture = CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0] + "runtime.INPUT_RECOVERY_DIAGNOSTICS.failure('delivery', OSError('synthetic diagnostic'))\nruntime.main()\n"
        (work/'fixture.py').write_text(CONTRACT_IMPORT_GUARD+fixture,encoding='utf-8')
        env=dict(os.environ,AURORA_INPUT_RECOVERY='durable',AURORA_ENABLE_TEXT_INPUT_PROCESS='0',AURORA_AUTH_MODE='api_key',PYTHONUNBUFFERED='1',AURORA_PYTHON=sys.executable)
        flags=['--offline','--lock-live','--no-ui','--no-live-init','--init-mode','skip','--no-chat-log-echo','--no-smoke-test','--no-sound','--action-mode','none']
        processes=[]
        try:
            for name,command in [('runtime',[sys.executable,str(work/'fixture.py'),*flags]),('panel',[sys.executable,str(Path(__file__).resolve()),'--worker',str(work)])]:
                with (work/f'{name}.log').open('w',encoding='utf-8') as log:
                    process=subprocess.Popen(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                processes.append(process)
                ownership.append(dict(role=name,pid=process.pid,started_at_epoch=time.time(),fixture_path=str(work)))
            processes[1].wait(timeout=100)
            assert processes[1].returncode==0,(work/'panel.log').read_text(encoding='utf-8',errors='replace')[-7000:]
            proof=json.loads((work/'proof.json').read_text(encoding='utf-8'))
            append_bridge_request(work,'SHUTDOWN_RUNTIME()',raw=True,client_id='fixture_cleanup')
            processes[0].wait(timeout=12)
            assert processes[0].returncode==0
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
                    process.wait(timeout=5)
        proof.update(ownership=ownership,elapsed_seconds=round(time.monotonic()-started,3),exit_codes=[p.returncode for p in processes])
    proof['fixture_removed']=not work.exists()
    return proof


if __name__=='__main__':
    if '--worker' in sys.argv: check_panel(Path(sys.argv[sys.argv.index('--worker')+1]))
    else: print(json.dumps(run_smoke(),indent=2))
