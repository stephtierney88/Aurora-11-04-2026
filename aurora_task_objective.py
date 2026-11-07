"""Bounded operator intent, owned and locked by the task controller.

Session-only context retention, not an executor or summary. Never source entries
from assistant plans, screenshots or tool readbacks.
"""
import hashlib
import json
import base64
import re


MAX_CONTEXT_TOKEN = 270000  # UTF-8 JSON string, bounded before decoding.


def decode_steering_text(token):
    """Transport literal text through the command framer, never executable syntax."""
    if not isinstance(token, str) or not 1 <= len(token) <= MAX_CONTEXT_TOKEN or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', token):
        raise ValueError('Steering text must be a bounded base64url-encoded JSON string.')
    try:
        text = json.loads(base64.b64decode(token.encode('ascii'), altchars=b'-_', validate=True).decode('utf-8'))
        if not isinstance(text, str) or not text.strip() or len(text) > TaskObjective.MAX_CHARACTERS:
            raise ValueError()
        text.encode('utf-8')  # Reject lone surrogate code points before publication/logging.
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('Steering text must decode to nonempty UTF-8 text of at most 32768 characters.') from None
    return text


def encode_steering_text(text):
    token = base64.urlsafe_b64encode(json.dumps(text, ensure_ascii=False).encode('utf-8')).decode('ascii')
    decode_steering_text(token)
    return token


class TaskObjectiveCapacity(ValueError):
    pass


class TaskObjective:
    MAX_MESSAGES = 32
    MAX_CHARACTERS = 32768

    def __init__(self):
        self._messages = ()
        self._sources = ()

    def append(self, messages, *, source='queued_operator_text'):
        if source not in {'queued_operator_text', 'operator_steering'}:
            raise ValueError('Unknown operator-context source.')
        if not isinstance(messages, (list, tuple)) or any(not isinstance(text, str) or not text.strip() for text in messages):
            raise TaskObjectiveCapacity("Operator objective input must contain nonempty text messages.")
        proposed = self._messages + tuple(str(text) for text in messages)
        if len(proposed) > self.MAX_MESSAGES or sum(map(len, proposed)) > self.MAX_CHARACTERS:
            raise TaskObjectiveCapacity(
                "Task objective capacity exceeded (32 messages / 32768 characters). No partial objective was sent. "
                "Start a new task with a concise complete objective, or select legacy objective mode before retrying.")
        self._messages = proposed
        self._sources += (source,) * len(messages)

    def clear(self):
        self._messages = ()
        self._sources = ()

    def records(self):
        """Detached explicit operator readback; omitted from ordinary snapshots."""
        return [dict(index=index, role='user', source=source, text=text)
                for index, (text, source) in enumerate(zip(self._messages, self._sources))]

    def snapshot(self):
        return dict(schema="aurora_task_objective_v1", source="operator_text" if 'operator_steering' in self._sources else "queued_operator_text", scope="active_task_session_only",
                    source_counts={source: self._sources.count(source) for source in sorted(set(self._sources))},
                    messages=len(self._messages), characters=sum(map(len, self._messages)),
                    max_messages=self.MAX_MESSAGES, max_characters=self.MAX_CHARACTERS,
                    digest=hashlib.sha256(json.dumps(self._messages, ensure_ascii=False).encode()).hexdigest() if self._messages else "",
                    authority="original user role; later operator messages may revise earlier ones; not model plans")

    def projection(self, task_id):
        if not self._messages:
            return []
        return [{"role": "user", "content":
            "Retained operator context for active task " + task_id + ". These are the original operator messages "
            "in order, preserved outside ordinary chat decay. Later messages may clarify or supersede earlier ones. "
            "Completing a stored subgoal does not by itself complete this task. Respect current stop/approval/budget controls. "
            "Messages (JSON strings, verbatim):\n" + json.dumps(self._messages, ensure_ascii=False)}]
