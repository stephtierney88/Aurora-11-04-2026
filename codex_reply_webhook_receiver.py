import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime


SCRIPT_DIR = Path(__file__).resolve().parent
INBOX_PATH = SCRIPT_DIR / "aurora_external_inbox.jsonl"
LOG_PATH = SCRIPT_DIR / "aurora_external_bridge_log.jsonl"


def append_record(text, source, subject, metadata):
    message_id = f"{int(datetime.now().timestamp() * 1000)}-{abs(hash((source, subject, text))) % 1000000}"
    record = {
        "message_id": message_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "author": "webhook",
        "source": source,
        "subject": subject,
        "text": text,
        "metadata": metadata or {},
    }
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INBOX_PATH.open("a", encoding="utf-8") as inbox:
        inbox.write(json.dumps(record, ensure_ascii=True) + "\n")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps({
            "timestamp": record["timestamp"],
            "event": "webhook_message_appended",
            "source": source,
            "message_id": message_id,
            "subject": subject,
        }, ensure_ascii=True) + "\n")
    return record


class Handler(BaseHTTPRequestHandler):
    shared_secret = ""

    def _write(self, status_code, body, content_type="application/json"):
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        validation_token = params.get("validationToken", [None])[0]
        if validation_token is not None:
            # Microsoft Graph webhook validation uses a plain-text echo.
            self._write(200, validation_token, content_type="text/plain")
            return
        if parsed.path == "/health":
            self._write(200, json.dumps({"ok": True, "path": "/health"}))
            return
        self._write(404, json.dumps({"ok": False, "reason": "not_found"}))

    def do_POST(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        validation_token = params.get("validationToken", [None])[0]
        if validation_token is not None:
            self._write(200, validation_token, content_type="text/plain")
            return

        if self.shared_secret:
            provided = self.headers.get("X-Codex-Token", "")
            if provided != self.shared_secret:
                self._write(403, json.dumps({"ok": False, "reason": "forbidden"}))
                return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = (self.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()

        payload = None
        if raw_body and content_type == "application/json":
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                payload = None

        source = "webhook"
        subject = "[CODEX] webhook reply"
        text = raw_body.strip()
        metadata = {"path": parsed.path, "content_type": content_type}

        if isinstance(payload, dict):
            if "text" in payload:
                text = str(payload.get("text", "")).strip()
            subject = str(payload.get("subject", subject)).strip() or subject
            source = str(payload.get("source", source)).strip() or source
            metadata["payload_keys"] = sorted(payload.keys())

            # Graph notifications usually do not contain the message body.
            if "value" in payload and not text:
                text = (
                    "Graph notification received. A follow-up Graph fetch is still required to read the "
                    "actual message body for this event."
                )
                source = "graph_notification"

        if not text:
            self._write(400, json.dumps({"ok": False, "reason": "empty_text"}))
            return

        record = append_record(text, source, subject, metadata)
        self._write(200, json.dumps({"ok": True, "message_id": record["message_id"], "source": source}))

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Local webhook receiver that writes inbound messages into aurora_external_inbox.jsonl. "
            "Useful as a generic relay target; Microsoft Graph message notifications still require "
            "separate token/app-registration work to fetch message contents."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--secret", default="")
    args = parser.parse_args()

    Handler.shared_secret = args.secret
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({
        "ok": True,
        "host": args.host,
        "port": args.port,
        "health_url": f"http://{args.host}:{args.port}/health",
    }))
    server.serve_forever()


if __name__ == "__main__":
    main()
