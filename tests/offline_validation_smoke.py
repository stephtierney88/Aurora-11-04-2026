"""Real-runtime VC1 recipes and cancellation, all provider/native I/O guarded."""
import json
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aurora_validation_console import PRESETS, ValidationService


def run_smoke():
    evidence = []
    with tempfile.TemporaryDirectory(prefix=".vc-proof-", dir=ROOT) as directory:
        service = ValidationService(ROOT, directory)
        try:
            for profile in list(PRESETS.values()) + [dict(PRESETS["effort"], name="Custom effort", baseline_effort="medium", changed_effort="xhigh")]:
                initial = service.start(profile, service.identity["fingerprint"], str(uuid.uuid4()))
                service.thread.join(70)
                assert not service.thread.is_alive()
                row = next(r for r in service.records("runs") if r["run_id"] == initial["run_id"])
                assert row["status"] == "passed", row
                assert row["result"]["restoration_verified"], row
                assert not row["result"]["guard_violations"], row
                assert row["cleanup"] == {"worker_stopped": True, "fixture_removed": True}, row
                evidence.append(row)
            initial = service.start(PRESETS["effort"], service.identity["fingerprint"], str(uuid.uuid4()))
            assert service.cancel(initial["run_id"])["status"] == "cancelling"
            try:
                service.start(PRESETS["model"], service.identity["fingerprint"], str(uuid.uuid4()))
            except ValueError:
                pass
            else:
                raise AssertionError("Concurrent run admitted")
            service.thread.join(70)
            row = next(r for r in service.records("runs") if r["run_id"] == initial["run_id"])
            assert row["status"] == "cancelled", row
            assert row["cleanup"] == {"worker_stopped": True, "fixture_removed": True}, row
            evidence.append(row)
        finally:
            service.close()
    return {"status": "passed", "source_fingerprint": service.identity["fingerprint"],
            "real_api_calls": 0, "native_input_capture": False, "owned_store_removed": not Path(directory).exists(),
            "runs": evidence}


if __name__ == "__main__":
    result = run_smoke()
    if len(sys.argv) == 2:
        Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, indent=2))
