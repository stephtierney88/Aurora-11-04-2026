"""Real routing/encoding/ledger with guarded fake HTTP/auth, never provider I/O."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    import copy
    from unittest.mock import patch
    import aurora_chatgpt_transport as subscription
    runtime.get_input_queue_store().get_nowait()
    operator("SET_LIVE_MODE(on); SET_TASK_MAX_MODEL_TURNS(30); SET_TASK_MAX_SECONDS(120)")
    runtime.API_KEY = "fake-fixture-only"
    runtime.DEFAULT_REASONING_EFFORT = "low"
    runtime.DEFAULT_SERVICE_TIER = "regular"
    runtime.AUTH_MODE = "api_key"
    runtime.MODEL_TRANSPORT = "chat_completions"
    runtime.perform_model_http_request = real_transport
    http_calls, turn_evidence = [], []
    http_mode = ['normal']
    late_release = threading.Event()

    class Response:
        def __init__(self, body, status=200):
            self.body, self.status_code, self.text = body, status, "fixture error"
            self.headers = {'x-request-id': 'req_fixture_'+str(len(http_calls)), 'Content-Type': 'text/event-stream'}
        def json(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def iter_lines(self):
            yield 'data: '+json.dumps({'type':'response.completed','response':self.body})
            yield ''

    def post(url, **kwargs):
        body = kwargs['json']
        http_calls.append({'transport': 'responses' if url.endswith('/responses') else 'chat_completions', 'model':body['model']})
        if http_mode[0] == 'cancel':
            runtime.MODEL_WORK.cancel('fixture cancellation')
            late_release.wait(2)
        if http_mode[0] == 'oauth_refresh' and len(http_calls) == refresh_start+1:
            return Response({},401)
        if http_mode[0] == 'error': return Response({},503)
        data = {'id':('resp_' if url.endswith('/responses') else 'chatcmpl_')+'fixture_'+str(len(http_calls)),
                'model':body['model'],'usage':{'input_tokens':2,'output_tokens':3,'total_tokens':5},
                'service_tier':'default','reasoning':{'effort':(body.get('reasoning') or {}).get('effort',body.get('reasoning_effort'))}}
        if url.endswith('/responses'):
            data.update(status='completed',output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Fixture response.'}]}])
        else: data['choices']=[{'message':{'content':reply[0]}}]
        return Response(data)

    def last_evidence():
        row=runtime.TASK_CONTINUATION.snapshot(include_progress=True)['progress']['requests'][-1]
        turn_evidence.append(copy.deepcopy(row))
        return row, row.get('transport_evidence',{})

    with patch.object(runtime.requests,'post',post):
        check('real API routing dispatches guarded request', input_turn('Inspect one API-key turn.'))
        row, evidence = last_evidence()
        check('prepared and actual transport are separate retained evidence', row['phase']=='responded' and row['prepared_settings']['configured_transport']=='chat_completions' and evidence['attempts'][0]['transport']=='chat_completions' and evidence['attempts'][0]['auth_mode']=='api_key')
        check('provider IDs are reported separately from local request ID', evidence['attempts'][0]['provider_request_id'].startswith('req_') and evidence['attempts'][0]['provider_response_id'].startswith('chatcmpl_') and row['inference_request_id'].startswith('turn-'))
        check('regular selection does not invent an explicit wire tier', row['prepared_settings']['service_tier']=='regular' and evidence['attempts'][0]['wire_service_tier'] is None and evidence['attempts'][0]['provider_reported_service_tier']=='default')
        reply[0]='Executed Commands:\nSHOW_TASK_STATUS()'
        input_turn('Exercise a typed command receipt.')
        receipt_row=runtime.TASK_CONTINUATION.snapshot(include_progress=True)['progress']['commands'][-1]
        families=receipt_row['receipt_evidence']['families']
        check('actual command worker contributes typed receipt evidence', any(r['family']=='task_control_results' and r['count']==1 for r in families))
        reply[0]='Ready.'

        class Auth:
            cache_path='fixture-cache'
            def __init__(self, **_kwargs): pass
            def get_api_access_token(self, force_refresh=False):
                if http_mode[0]=='auth_error': raise runtime.CodexOAuthError('fixture rejection')
                return 'fixture-oauth'
        with patch.object(runtime,'CodexOAuthManager',Auth):
            runtime.AUTH_MODE='auto'; http_mode[0]='oauth_refresh'; refresh_start=len(http_calls)
            check('legacy auth-refresh behavior retained', input_turn('Inspect refresh attempt.'))
            row,evidence=last_evidence()
            check('refresh records both exact HTTP attempts', [a['http_status'] for a in evidence['attempts']]==[401,200] and all(a['auth_mode']=='codex_oauth' for a in evidence['attempts']))
            runtime.AUTH_MODE='codex_oauth'; http_mode[0]='auth_error'; before=len(http_calls)
            input_turn('Exercise preflight failure.')
            row,evidence=last_evidence()
            check('path started does not claim an inference HTTP attempt', row['phase']=='failed' and evidence['worker_failed'] and evidence['instrumented'] and not evidence['attempts'] and len(http_calls)==before)
            runtime.AUTH_MODE='auto'
            input_turn('Inspect the existing automatic API-key fallback.')
            row,evidence=last_evidence()
            check('auto auth records actual fallback rather than configured mode', row['phase']=='responded' and row['prepared_settings']['configured_auth']=='auto' and evidence['attempts'][0]['auth_mode']=='api_key')

        http_mode[0]='normal'; runtime.AUTH_MODE='api_key'; runtime.MODEL_TRANSPORT='responses'
        runtime.ACTIVE_TEXT_MODEL=runtime.ACTIVE_VISION_MODEL=runtime.ACTIVE_REASONING_MODEL=runtime.ASTRA_MODEL
        runtime.RESPONSES_REASONING.reset('fixture')
        operator('SET_NEXT_REASONING_EFFORT(high)')
        check('adaptive Responses still runs', input_turn('Inspect adaptive effort.'))
        row,evidence=last_evidence()
        check('configuration update selection is distinct from request-level and reported effort', evidence['controller_selected_effort']=='high' and evidence['configuration_update_sent'] and evidence['attempts'][0]['wire_reasoning_effort']=='low' and evidence['attempts'][0]['provider_reported_effort']=='low')
        check('one-turn effort restoration still runs', input_turn('Inspect restoration.'))
        row,evidence=last_evidence()
        check('restoration evidence belongs to next exact request', evidence['controller_selected_effort']=='low' and evidence['configuration_update_sent'])

        runtime.AUTH_MODE='openai_chatgpt'; runtime.SUBSCRIPTION_POLICY='legacy'
        profile={'slug':runtime.ASTRA_MODEL,'service_tiers':[],'supported_reasoning_levels':[{'effort':'low'}], 'support_verbosity':True}
        fake_auth=SimpleNamespace(access=lambda:('fixture-subscription','PRIVATE_ACCOUNT'))
        with patch.object(subscription,'ChatGPTAuth',return_value=fake_auth), patch.object(subscription,'account_models',return_value=('PRIVATE_ACCOUNT',[profile])):
            check('subscription translation still runs',input_turn('Inspect subscription transport.'))
            row,evidence=last_evidence()
            check('effective subscription route overrides configured Responses mode', evidence['attempts'][0]['transport']=='chatgpt_subscription_responses' and evidence['attempts'][0]['auth_mode']=='openai_chatgpt')
            check('completed stream metadata survives response wrapper',evidence['attempts'][0]['provider_response_id'].startswith('resp_') and evidence['attempts'][0]['provider_reported_effort']=='low')

        runtime.AUTH_MODE='api_key';runtime.MODEL_TRANSPORT='chat_completions';http_mode[0]='error'
        input_turn('Inspect HTTP error.')
        row,evidence=last_evidence()
        check('HTTP failure retained without invented completion ID',row['phase']=='failed' and evidence['attempts'][0]['http_status']==503 and evidence['attempts'][0]['provider_response_id'] is None)
        http_mode[0]='cancel'
        try:
            input_turn('Cancel an in-flight request.')
            row,evidence=last_evidence()
            check('cancelled turn freezes before late response', row['phase']=='cancelled' and evidence['observation_closed'] and not evidence['attempts'][0]['http_response_observed'])
        finally: late_release.set()
        deadline=time.monotonic()+3
        while runtime.MODEL_IO.busy and time.monotonic()<deadline: time.sleep(.01)
        check('late response cannot rewrite request history', not runtime.MODEL_IO.busy and runtime.TASK_CONTINUATION.snapshot(include_progress=True)['progress']['requests'][-1]==row)
        check('transport evidence contains no account credentials or bodies', all(word not in json.dumps(turn_evidence) for word in ('PRIVATE_ACCOUNT','fixture-only','fixture-oauth','fixture-subscription','Authorization','Fixture response.')))
    runtime.SEND_TO_MODEL=runtime.ENABLE_MODEL_RESPONSES=False
'''


def run_smoke():
    marker='    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    fixture=continuation.SCENARIOS.replace('runtime.perform_model_http_request = provider',
        'real_transport = guarded_original_transport\nruntime.perform_model_http_request = provider')
    fixture=fixture.replace(marker,SCENARIOS+'\n'+marker)
    fixture=fixture.replace('"requests": calls,','"requests": calls, "transport_evidence": turn_evidence, "fake_http_calls": len(http_calls),')
    guarded = continuation.CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0].replace(
        'runtime.perform_model_http_request = forbidden_input("perform_model_http_request")',
        'guarded_original_transport = runtime.perform_model_http_request\nruntime.perform_model_http_request = forbidden_input("perform_model_http_request")')
    continuation.harness.FIXTURE=continuation.CONTRACT_IMPORT_GUARD+guarded+fixture
    return continuation.harness.run_smoke()


if __name__=='__main__': print(json.dumps(run_smoke(),indent=2))
