"""Receipt-backed recovered-input browser; the runtime remains the write authority."""
import copy
import time
import tkinter as tk
from tkinter import ttk

from aurora_control_plane import control_plane_paths, journal_offsets, read_jsonl_batch, extract_request_identity
from aurora_input_recovery import ACTIVE, PHASES, RESULT_SCHEMA, identity_key, is_digest, parse_arguments
from aurora_panel_layout import FlowBar, ui_scale

PAGE_SIZE = 10
NOTICE = ("Retry queues the original text using current context/settings. If inference is enabled, it may run immediately. "
          "Closing this window does not cancel input. Cancel queued input does not undo actions or stop remote work.")


def readiness_text(state, fresh):
    """Keep missing/old evidence distinct from a currently usable store."""
    if state.get('schema_version') != 'aurora_input_recovery_readiness_v1':
        return 'Recovery readiness unknown: this export has no readiness evidence.', None
    prefix = '' if fresh else 'Historical export; runtime unavailable or state stale. '
    counts = {key: state.get(key) if type(state.get(key)) is int else 'unknown' for key in ('held', 'uncertain', 'active')}
    text = (f"{prefix}Effective recovery: {state.get('effective_mode', 'unknown')} · "
            f"startup: {state.get('startup_mode', 'unknown')} ({state.get('startup_source', 'unknown')}) · "
            f"store: {state.get('store_state', 'unknown')} · last write: {state.get('last_write', 'unknown')}. "
            f"Held {counts['held']} · uncertain {counts['uncertain']} · active {counts['active']}. ")
    diagnostic = state.get('diagnostic') or {}
    version = diagnostic.get('version')
    if is_digest(version):
        text += (f"Last diagnostic: {diagnostic.get('operation', 'unknown')} / {diagnostic.get('error_type', 'unknown')} "
                 f"({'seen' if diagnostic.get('acknowledged') else 'unacknowledged'}). Seeing it does not repair or authorize retry. ")
    else:
        version = None
    text += 'No automatic replay. Open store does not guarantee future writes.'
    return text, version if fresh and not diagnostic.get('acknowledged') else None


def recovery_actions(row):
    """Presentation hints only; runtime admission checks every action again."""
    eligible = bool(row) and row.get('phase') in PHASES - ACTIVE - {'responded'}
    return dict(cancel=eligible, retry=eligible and row['phase'] != 'queued',
                acknowledgement=bool(row) and (row.get('request_started') is True or row.get('phase') == 'uncertain'))


def recovery_command(name, row, acknowledge=False):
    args = [row['entry_id'], row['version']]
    if name == 'RETRY_INPUT' and acknowledge:
        args.append('allow_uncertain')
    parse_arguments(name, args)
    return name + '(' + ','.join(args) + ')'


def recovery_page(receipt):
    """Accept a complete, correlated SHOW readback, not success inferred from activity."""
    results = receipt.get('memory_command_results') or []
    result = next((r for r in results if r.get('command') == 'SHOW_INPUT_RECOVERY'), None)
    if not result or result.get('schema_version') != RESULT_SCHEMA or result.get('success') is not True:
        raise ValueError((result or {}).get('reason') or receipt.get('reason') or 'No successful recovery readback.')
    page = result.get('readback') or {}
    if any(type(page.get(k)) is not int or page[k] < 0 for k in ('total', 'offset', 'omitted_before', 'omitted')):
        raise ValueError('Incomplete recovery pagination.')
    entries = page.get('entries')
    if not isinstance(entries, list) or len(entries) > PAGE_SIZE:
        raise ValueError('Invalid recovery page size.')
    keys = set()
    for row in entries:
        parse_arguments('CANCEL_QUEUED_INPUT', [row.get('entry_id'), row.get('version')])
        if (row['entry_id'] in keys or identity_key(row.get('original_identity')) != row['entry_id']
                or row.get('phase') not in PHASES or not isinstance(row.get('text'), str)
                or len(row['text']) > 64000 or type(row.get('attempt')) is not int or row['attempt'] < 1
                or type(row.get('request_started')) is not bool):
            raise ValueError('Invalid recovery row.')
        identity_key(row.get('identity'))
        keys.add(row['entry_id'])
    if page['omitted_before'] + len(entries) + page['omitted'] != page['total']:
        raise ValueError('Inconsistent recovery pagination.')
    return copy.deepcopy(page)


class RecoveryReceiptClient:
    """Bounded incremental polling, no background worker or automatic resend."""
    def __init__(self, root, send, *, clock=time.monotonic):
        self.paths, self.root, self.send, self.clock = control_plane_paths(root), root, send, clock
        self.pending = None

    def start(self, command):
        if self.pending:
            raise ValueError('Wait for the current recovery receipt.')
        positions = journal_offsets(self.root)
        cursors = {}
        for key in positions:
            try:
                stat = self.paths[key].stat()
                file_id = f'{stat.st_dev}:{stat.st_ino}'
            except FileNotFoundError:
                file_id = ''
            cursors[key] = dict(offset=positions[key], file_identity=file_id, discarding_record=False)
        record = self.send(command)
        identity = extract_request_identity(record)
        identity_key(identity)
        self.pending = dict(identity=identity, cursors=cursors, deadline=self.clock()+20)
        return record

    def poll(self):
        pending = self.pending
        if not pending:
            return None
        try:
            for key, cursor in pending['cursors'].items():
                batch = read_jsonl_batch(self.paths[key], **cursor, max_records=64,
                                        max_record_bytes=8*1024*1024, max_bytes=8*1024*1024+1)
                cursor.update(offset=batch['next_offset'], file_identity=batch['file_identity'],
                              discarding_record=batch['discarding_record'])
                for entry in batch['entries']:
                    row = entry['record'] or {}
                    if extract_request_identity(row) != pending['identity']:
                        continue
                    if ((key == 'command_log' and row.get('event') == 'command_result' and row.get('terminal', True))
                            or (key == 'bridge_log' and row.get('event') == 'message_rejected')):
                        self.pending = None
                        return row
            if self.clock() >= pending['deadline']:
                self.pending = None
                return dict(terminal=False, reason='Receipt timed out; outcome unknown. Refresh before another action. No automatic retry.')
        except Exception:
            self.pending = None
            return dict(terminal=False, reason='Receipt unavailable; outcome unknown. Refresh before another action. No automatic retry.')
        return None


class RecoveryPane(ttk.Frame):
    """Manual paged inspection inside Outbox; no direct read/write of recovery JSON."""
    def __init__(self, parent, app, root):
        super().__init__(parent, padding=12)
        scale = ui_scale(self)
        self.app = app
        self.client = RecoveryReceiptClient(root, app.send_raw)
        self.page, self.rows, self.valid = None, {}, False
        self.offset, self.operation, self.last_receipt = 0, '', None
        self._after, self._selected_version, self._mode = None, None, None
        self._diagnostic_version = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(4, weight=2)
        self.summary = tk.StringVar(value='Select Refresh to inspect runtime-owned recovery records.')
        self.status = tk.StringVar(value=NOTICE)
        self.acknowledge = tk.BooleanVar(value=False)
        for row_index, variable in ((0, self.summary), (6, self.status)):
            label = ttk.Label(self, textvariable=variable, wraplength=550)
            label.grid(row=row_index, column=0, sticky='ew', pady=(0, 8))
            label.bind('<Configure>', lambda e, label=label: label.configure(wraplength=max(100, e.width)))
        actions = FlowBar(self)
        actions.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.reload = actions.add(ttk.Button(actions, text='Refresh records', command=self.load))
        self.refresh_status = actions.add(ttk.Button(actions, text='Refresh status', command=lambda:
            self.submit('SHOW_INPUT_RECOVERY_STATUS', 'SHOW_INPUT_RECOVERY_STATUS()')))
        self.ack_diagnostic = actions.add(ttk.Button(actions, text='Acknowledge diagnostic', command=self.acknowledge_diagnostic))
        self.previous = actions.add(ttk.Button(actions, text='Previous page', command=lambda: self.load(max(0,self.offset-PAGE_SIZE))))
        self.next = actions.add(ttk.Button(actions, text='Next page', command=lambda: self.load(self.offset+PAGE_SIZE)))
        actions.add(ttk.Button(actions, text='Recovery settings', command=self.settings))
        area = ttk.Frame(self)
        area.grid(row=2, column=0, sticky='nsew')
        self.tree = ttk.Treeview(area, columns=('phase','attempt','text'), show='headings', selectmode='browse', height=4, style='Outbox.Treeview')
        for key, title, width in (('phase','Recorded state',150),('attempt','Attempt',65),('text','Message',300)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=round(width*scale), minwidth=round(45*scale), stretch=key=='text')
        scroll = ttk.Scrollbar(area, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        controls = FlowBar(self)
        controls.grid(row=3, column=0, sticky='ew', pady=8)
        self.cancel = controls.add(ttk.Button(controls, text='Cancel queued input', command=lambda: self.act('CANCEL_QUEUED_INPUT')))
        self.retry = controls.add(ttk.Button(controls, text='Queue selected retry', command=lambda: self.act('RETRY_INPUT')))
        area = ttk.Frame(self)
        area.grid(row=4, column=0, sticky='nsew')
        self.details = tk.Text(area, height=7, width=30, wrap='word', bg='#151f30', fg='#e1e9f5', state='disabled', padx=10, pady=8)
        scroll = ttk.Scrollbar(area, command=self.details.yview)
        self.details.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.details.pack(fill='both', expand=True)
        self.details.bind('<Tab>', lambda e: (self.details.tk_focusNext().focus_set(), 'break')[1])
        self.details.bind('<Shift-Tab>', lambda e: (self.details.tk_focusPrev().focus_set(), 'break')[1])
        self.ack = ttk.Checkbutton(self, text='I inspected the prior request;\nretry may duplicate effects', variable=self.acknowledge, command=self.update_controls)
        self.ack.grid(row=5, column=0, sticky='w', pady=8)
        self.bind('<Destroy>', self.closed, add='+')
        self.update_controls()

    def settings(self):
        self.app.switchboard.focus_setting('conversation.input_recovery')
        self.app.deiconify()
        self.app.lift()
        self.status.set('Revealed Durable input recovery in The Switchboard. Pause inference and empty the queue before changing mode. Default legacy; durable stores full input text locally. Edit, preview and apply there.')

    def runtime_fresh(self):
        try:
            status, _ = self.app._get_control_panel_settings_snapshot()
            age = (status.get('state') or {}).get('age_seconds')
            fresh = bool((status.get('runtime') or {}).get('running')) and age is not None and 0 <= age <= 10
        except Exception:
            fresh = False
        return fresh

    def readiness(self):
        return ((self.app.state_cache or {}).get('conversation_io') or {}).get('input_recovery_readiness') or {}

    def availability(self):
        mode = ((self.app.state_cache or {}).get('modes') or {}).get('input_recovery', 'unknown')
        state = self.readiness()
        opened = state.get('records_available') is True if state.get('schema_version') == 'aurora_input_recovery_readiness_v1' else True
        return self.runtime_fresh() and mode == 'durable' and opened, mode

    def acknowledge_diagnostic(self):
        # Submit the version actually displayed; a newer fault must reject this command.
        if self._diagnostic_version:
            return self.submit('ACK_INPUT_RECOVERY_DIAGNOSTIC',
                               f'ACK_INPUT_RECOVERY_DIAGNOSTIC({self._diagnostic_version})')

    def update_controls(self):
        available, mode = self.availability()
        if not available or mode != self._mode:
            self.valid = False
            self.acknowledge.set(False)
        self._mode = mode
        ready = available and not self.client.pending
        fresh = self.runtime_fresh()
        explanation, self._diagnostic_version = readiness_text(self.readiness(), fresh)
        row = self.selected()
        actions = recovery_actions(row)
        enabled = dict(reload=ready, previous=ready and self.offset>0,
                       refresh_status=fresh and not self.client.pending,
                       ack_diagnostic=bool(self._diagnostic_version) and not self.client.pending,
                       next=ready and self.valid and bool((self.page or {}).get('omitted')),
                       cancel=ready and self.valid and actions['cancel'],
                       retry=ready and self.valid and actions['retry'] and (not actions['acknowledgement'] or self.acknowledge.get()),
                       ack=ready and self.valid and actions['retry'] and actions['acknowledgement'])
        for name, value in enabled.items():
            getattr(self,name).state(['!disabled'] if value else ['disabled'])
        if not available:
            summary = f'Recovery mode: {mode}. Records need a fresh runtime with an open durable store. Use Recovery settings while paused; inspect diagnostics if opening failed.'
        elif self.page:
            summary = (f"Durable recovery · {len(self.rows)} shown / {self.page['total']} retained · {self.page['omitted_before']} before / {self.page['omitted']} after · {self.page.get('compacted',0)} compacted (duplicate protection retained). "
                       + ('Snapshot from the last Refresh; runtime rechecks versions.' if self.valid else 'Refresh required before another action.'))
        else:
            summary = 'Durable recovery enabled. Refresh to read held, uncertain and completed inputs. Nothing automatically retries.'
        summary = explanation + '\n' + summary
        if self.summary.get() != summary:
            self.summary.set(summary)

    def selected(self):
        selection = self.tree.selection()
        return self.rows.get(selection[0]) if selection else None

    def select(self, _event=None):
        row = self.selected()
        version = (row['entry_id'], row['version']) if row else None
        if version != self._selected_version:
            self.acknowledge.set(False)
            self._selected_version = version
        text = 'Select a retained input to inspect its exact text and original/retry identities.'
        if row:
            text = (f"State: {row['phase']} · Attempt {row['attempt']} · Request started: {row['request_started']}\n"
                    f"Turn: {row.get('turn_id') or 'not observed'}\nEntry: {row['entry_id']}\nVersion: {row['version']}\n")
            for title, key in (('Original input','original_identity'),('Current attempt','identity')):
                identity = row[key]
                text += f"\n{title}\nClient: {identity['client_id']}\nRequest: {identity['request_id']}\nMessage: {identity['message_id']}\n"
            text += '\nExact retained input\n' + row['text']
        if self.details.get('1.0','end-1c') != text:
            self.details.configure(state='normal')
            self.details.delete('1.0','end')
            self.details.insert('1.0',text)
            self.details.configure(state='disabled')
        self.update_controls()

    def load(self, offset=None):
        offset = self.offset if offset is None else offset
        return self.submit('SHOW_INPUT_RECOVERY', f'SHOW_INPUT_RECOVERY({offset},{PAGE_SIZE})')

    def act(self, name):
        self.update_controls()
        row = self.selected()
        actions = recovery_actions(row)
        if not self.valid or not row or not actions['retry' if name=='RETRY_INPUT' else 'cancel']:
            self.status.set('Refresh and select an eligible input first. Active requests use Cancel work.')
            return
        if name=='RETRY_INPUT' and actions['acknowledgement'] and not self.acknowledge.get():
            self.status.set('Inspect the prior request and explicitly acknowledge possible duplicate effects before retrying.')
            return
        return self.submit(name, recovery_command(name,row,name=='RETRY_INPUT' and self.acknowledge.get()))

    def submit(self, operation, command):
        available, _ = self.availability()
        if operation in {'SHOW_INPUT_RECOVERY_STATUS', 'ACK_INPUT_RECOVERY_DIAGNOSTIC'}:
            available = self.runtime_fresh()
        if not available or self.client.pending:
            self.status.set('A fresh durable runtime and no pending recovery request are required.')
            return
        self.valid = False
        self.acknowledge.set(False)
        try:
            self.client.start(command)
            self.operation = operation
            self.status.set('Queued control request; waiting for its exact receipt. ' + NOTICE)
            self._after = self.after(100, self.poll)
        except Exception as error:
            self.status.set(f'Submission unconfirmed ({type(error).__name__}); refresh before another action. No automatic retry.')
        self.update_controls()

    def poll(self):
        self._after = None
        receipt = self.client.poll()
        if receipt is None:
            if self.client.pending:
                self._after = self.after(150, self.poll)
            return
        self.last_receipt = receipt
        try:
            if self.operation == 'SHOW_INPUT_RECOVERY':
                page = recovery_page(receipt)
                self.page, self.offset = page, page['offset']
                self.rows = {row['entry_id']:row for row in page['entries']}
                old = set(self.tree.get_children())
                for key, row in self.rows.items():
                    values = (row['phase'], row['attempt'], ' '.join(row['text'].split())[:180])
                    self.tree.item(key,values=values) if key in old else self.tree.insert('','end',iid=key,values=values)
                for key in old-self.rows.keys():
                    self.tree.delete(key)
                if not self.tree.selection() and self.rows:
                    self.tree.selection_set(next(iter(self.rows)))
                self.valid = True
                self.status.set('Recovery snapshot received. ' + NOTICE)
                self.select()
            else:
                results = receipt.get('memory_command_results') or []
                result = next((r for r in results if r.get('command')==self.operation and r.get('schema_version')==RESULT_SCHEMA), {})
                if result.get('success') is not True:
                    raise ValueError(result.get('reason') or receipt.get('reason') or 'Action not confirmed.')
                if self.operation in {'SHOW_INPUT_RECOVERY_STATUS', 'ACK_INPUT_RECOVERY_DIAGNOSTIC'}:
                    state = result.get('readback') or result.get('after') or {}
                    explanation, _ = readiness_text(state, True)
                    self.status.set('Confirmed ' + self.operation + ': ' + explanation)
                else:
                    row = result.get('after') or {}
                    self.status.set(f"Confirmed {self.operation}: {row.get('phase','unknown')}, attempt {row.get('attempt','unknown')}. "
                                    'Refresh to inspect the new version and retry identity. ' + NOTICE)
        except Exception as error:
            self.valid = False
            self.status.set(str(error) + ' Refresh before another action; no automatic retry.')
        self.update_controls()

    def closed(self, event):
        if event.widget is self and self._after is not None:
            self.after_cancel(self._after)
            self._after = None
