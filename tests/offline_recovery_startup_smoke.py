"""Fail-closed real main() prerequisites with guarded native/network boundaries."""
import json
import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

SCENARIOS = r'''
import json
from aurora_input_recovery import InputRecovery
checks = []
def check(name, value):
    assert value, name
    checks.append(name)
path = Path('aurora_input_recovery.json')
def failed_start(label):
    try: runtime.main()
    except (OSError, ValueError): pass
    else: raise AssertionError('Startup unexpectedly succeeded: ' + label)
    state = json.loads(Path('aurora_control_panel_state.json').read_text(encoding='utf-8'))
    ready = state['conversation_io']['input_recovery_readiness']
    check(label + ': fail-closed readiness exported', ready['effective_mode']=='durable'
          and ready['startup_mode']=='durable' and ready['startup_source']=='AURORA_INPUT_RECOVERY'
          and ready['store_state']=='not_open' and not ready['records_available']
          and ready['diagnostic']['operation']=='open')
    check(label + ': no queue or model call', runtime.get_input_queue_store().empty()
          and runtime.INPUT_RECOVERY is None and not runtime.MODEL_IO.busy)
    return ready
path.write_text('{corrupt fixture', encoding='utf-8')
before = path.read_bytes()
first = failed_start('corrupt store')
check('corrupt evidence unchanged', path.read_bytes()==before)
path.write_text(json.dumps(dict(schema_version='aurora_input_recovery_v1', rows={})), encoding='utf-8')
owner = InputRecovery(path)
try:
    second = failed_start('leased store')
    check('second failure has new diagnostic identity', first['diagnostic']['version']!=second['diagnostic']['version'])
finally:
    owner.close()
check('failed starts never wrote runtime PID', not Path(runtime.runtime_pid_path).exists())
check('no native or network guard touched', not Path('forbidden-native-input.txt').exists())
Path('proof.json').write_text(json.dumps(dict(status='passed',checks=checks,check_count=len(checks),real_api_calls=0,native_calls=0)), encoding='utf-8')
'''

def run_smoke():
    harness.FIXTURE = "import os\nos.environ['AURORA_INPUT_RECOVERY']='durable'\n" + CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0] + SCENARIOS
    return harness.run_smoke()

if __name__ == '__main__': print(json.dumps(run_smoke(), indent=2))
