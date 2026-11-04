import argparse
import email
import hashlib
import imaplib
import json
import os
import sys
import time
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parseaddr
from getpass import getpass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INBOX_PATH = SCRIPT_DIR / "aurora_external_inbox.jsonl"
LOG_PATH = SCRIPT_DIR / "aurora_external_bridge_log.jsonl"
STATE_PATH = SCRIPT_DIR / "gmail_reply_bridge_state.json"


def env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def load_state():
    default_state = {"processed_uids": {}, "last_poll_at": ""}
    if not STATE_PATH.exists():
        return default_state
    try:
        loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            merged = dict(default_state)
            merged.update(loaded)
            if not isinstance(merged.get("processed_uids"), dict):
                merged["processed_uids"] = {}
            return merged
    except Exception:
        pass
    return default_state


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def log_event(event_type, **fields):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event": event_type,
    }
    record.update(fields)
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=True) + "\n")
    preview = {
        "event": event_type,
        "uid": fields.get("uid", ""),
        "subject": fields.get("subject", ""),
        "source": fields.get("source", ""),
    }
    print("[GMAIL-BRIDGE]", json.dumps(preview, ensure_ascii=True))


def decode_mime_header(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def normalize_address(value):
    _, address = parseaddr(value or "")
    return address.strip().lower()


def extract_text_from_message(message):
    text_chunks = []

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition", "") or "").lower()
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    text_chunks.append(payload.decode(charset, errors="replace"))
                except Exception:
                    text_chunks.append(payload.decode("utf-8", errors="replace"))
    else:
        payload = message.get_payload(decode=True) or b""
        charset = message.get_content_charset() or "utf-8"
        try:
            text_chunks.append(payload.decode(charset, errors="replace"))
        except Exception:
            text_chunks.append(payload.decode("utf-8", errors="replace"))

    text = "\n".join(chunk.strip() for chunk in text_chunks if chunk and chunk.strip())
    return strip_quoted_reply(text)


def strip_quoted_reply(text):
    if not text:
        return ""
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if stripped.startswith(">"):
            break
        if lowered.startswith("on ") and " wrote:" in lowered:
            break
        if lowered.startswith("from: ") or lowered.startswith("sent: ") or lowered.startswith("subject: "):
            break
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def is_codex_notification_template(subject, body_text, message):
    normalized_subject = (subject or "").strip().lower()
    normalized_body = (body_text or "").strip().lower()
    in_reply_to = (message.get("In-Reply-To", "") or "").strip()
    references = (message.get("References", "") or "").strip()

    if in_reply_to or references:
        return False

    if not normalized_subject.startswith("[codex]"):
        return False

    template_markers = [
        "codex finished the requested task.",
        "codex gmail bridge live test",
        "reply to this email with a short body like:",
        "reply to this email or send a new email with subject starting [codex]",
    ]
    return any(marker in normalized_body for marker in template_markers)


def append_external_message(text, source, subject, author, uid, metadata=None):
    normalized = (text or "").strip()
    if not normalized:
        return None

    record = {
        "message_id": f"{int(time.time() * 1000)}-{abs(hash((uid, subject, normalized))) % 1000000}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "author": author,
        "source": source,
        "subject": subject,
        "text": normalized,
        "metadata": metadata or {},
    }
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INBOX_PATH.open("a", encoding="utf-8") as inbox:
        inbox.write(json.dumps(record, ensure_ascii=True) + "\n")
    log_event("gmail_message_appended", source=source, uid=uid, subject=subject)
    return record


def connect_imap(username, password, host):
    client = imaplib.IMAP4_SSL(host, timeout=30)
    client.login(username, password)
    return client


def search_candidate_uids(client, mailbox, subject_prefix, allowed_senders, max_candidates=25):
    status, _ = client.select(mailbox)
    if status != "OK":
        raise RuntimeError(f"Unable to select mailbox {mailbox!r}")

    primary_sender = ""
    if allowed_senders:
        primary_sender = sorted(allowed_senders)[0]

    gmail_query_terms = ["is:unread", "newer_than:14d"]
    if subject_prefix:
        gmail_query_terms.append(f"subject:{subject_prefix}")
    if primary_sender:
        gmail_query_terms.append(f"from:{primary_sender}")
    gmail_query = " ".join(gmail_query_terms)

    status, data = client.uid("SEARCH", None, "X-GM-RAW", f'"{gmail_query}"')
    if status != "OK":
        search_args = ["UNSEEN", "SINCE", datetime.now().strftime("%d-%b-%Y")]
        if subject_prefix:
            search_args.extend(["HEADER", "SUBJECT", f'"{subject_prefix}"'])
        if primary_sender:
            search_args.extend(["FROM", f'"{primary_sender}"'])
        status, data = client.uid("SEARCH", None, *search_args)
    if status != "OK":
        raise RuntimeError("IMAP search failed")

    candidates = []
    for uid in (data[0] or b"").split():
        if uid:
            candidates.append(uid.decode("ascii", errors="ignore"))
    return candidates[-max_candidates:]


def fetch_message_by_uid(client, uid):
    status, data = client.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
    if status != "OK":
        raise RuntimeError(f"IMAP fetch failed for UID {uid}")

    for item in data:
        if isinstance(item, tuple):
            return email.message_from_bytes(item[1])
    raise RuntimeError(f"No message payload returned for UID {uid}")


def mark_seen(client, uid):
    client.uid("STORE", uid, "+FLAGS", "(\\Seen)")


def poll_once(username, password, host, mailbox, allowed_senders, subject_prefix, state):
    client = connect_imap(username, password, host)
    ingested = 0
    try:
        candidate_uids = search_candidate_uids(client, mailbox, subject_prefix, allowed_senders)
        for uid in candidate_uids:
            if uid in state["processed_uids"]:
                continue

            message = fetch_message_by_uid(client, uid)
            subject = decode_mime_header(message.get("Subject", ""))
            sender = normalize_address(message.get("From", ""))

            if subject_prefix and subject_prefix not in subject:
                continue
            if allowed_senders and sender not in allowed_senders:
                continue

            body_text = extract_text_from_message(message)
            if not body_text:
                log_event("gmail_message_skipped_empty", uid=uid, subject=subject, source=sender)
                state["processed_uids"][uid] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                mark_seen(client, uid)
                continue

            if is_codex_notification_template(subject, body_text, message):
                log_event("gmail_message_skipped_notification", uid=uid, subject=subject, source=sender)
                state["processed_uids"][uid] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                mark_seen(client, uid)
                continue

            append_external_message(
                body_text,
                source="gmail_imap",
                subject=subject,
                author=sender or "gmail_user",
                uid=uid,
                metadata={"from": sender, "mailbox": mailbox},
            )
            state["processed_uids"][uid] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mark_seen(client, uid)
            ingested += 1

        state["last_poll_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Keep the state bounded.
        if len(state["processed_uids"]) > 500:
            items = sorted(state["processed_uids"].items(), key=lambda kv: kv[1], reverse=True)[:300]
            state["processed_uids"] = dict(items)
        save_state(state)
        return ingested
    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Poll a Gmail inbox via IMAP and append qualifying replies into "
            "aurora_external_inbox.jsonl for Aurora/Codex to ingest."
        )
    )
    parser.add_argument("--username", default=env("AURORA_GMAIL_USERNAME", "user@example.com"))
    parser.add_argument("--app-password", default=env("AURORA_GMAIL_APP_PASSWORD"))
    parser.add_argument("--imap-host", default=env("AURORA_GMAIL_IMAP_HOST", "imap.gmail.com"))
    parser.add_argument("--mailbox", default=env("AURORA_GMAIL_MAILBOX", "INBOX"))
    parser.add_argument("--subject-prefix", default=env("AURORA_GMAIL_SUBJECT_PREFIX", "[CODEX]"))
    parser.add_argument("--allowed-from", default=env("AURORA_GMAIL_ALLOWED_FROM", "user@example.com"))
    parser.add_argument("--poll-seconds", type=int, default=int(env("AURORA_GMAIL_POLL_SECONDS", "30") or "30"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    app_password = args.app_password
    if not app_password:
        if args.once or sys.stdin.isatty():
            app_password = getpass("Gmail app password: ")
        else:
            raise SystemExit("Missing Gmail app password. Set AURORA_GMAIL_APP_PASSWORD or run interactively.")

    allowed_senders = {
        normalize_address(item)
        for item in (args.allowed_from or "").split(",")
        if normalize_address(item)
    }

    state = load_state()
    log_event("gmail_bridge_started", source="gmail_imap", subject=args.subject_prefix)

    while True:
        try:
            ingested = poll_once(
                username=args.username,
                password=app_password,
                host=args.imap_host,
                mailbox=args.mailbox,
                allowed_senders=allowed_senders,
                subject_prefix=args.subject_prefix,
                state=state,
            )
            if ingested:
                print(json.dumps({"ok": True, "ingested": ingested}))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log_event("gmail_bridge_error", source="gmail_imap", subject=str(exc))
            print(json.dumps({"ok": False, "error": str(exc)}))

        if args.once:
            break
        time.sleep(max(5, args.poll_seconds))


if __name__ == "__main__":
    main()
