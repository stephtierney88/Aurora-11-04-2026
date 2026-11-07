"""Read-only, bounded inspection of exported or explicitly loaded historical tasks.

No executor, provider call, pixel display or automatic refresh. Explicit history
readers are separate from the current export and never restore runtime state.
Linked records are latest retained evidence in this frozen snapshot, not as-of
state at an event. Missing evidence is never filled from a different task.
"""
import copy
import json
import datetime
import time
import uuid
import tkinter as tk
from tkinter import ttk

from aurora_capture_artifacts import ArtifactCheck
from aurora_execution_projection import LIMIT, NOTICE, FIELDS, NESTED, inspection_snapshot, inspection_detail
from aurora_execution_history import NOTICE as HISTORY_NOTICE
from aurora_execution_history_job import HistoryJob
from pathlib import Path
from aurora_panel_layout import FlowBar, bind_label_wrap, fit_popout_window, reconcile_tree_rows, ui_scale


class ExecutionInspector(tk.Toplevel):
    """One reusable view; explicit snapshot replacement and bounded owned I/O jobs."""
    @classmethod
    def open(cls, app):
        current = getattr(app, 'execution_inspector', None)
        if current is not None and current.winfo_exists():
            current.deiconify()
            current.lift()
            return current
        app.execution_inspector = cls(app)
        return app.execution_inspector

    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self.app, self.snapshot, self.identities = app, {}, {}
        self.artifact_check, self.artifact_job, self.artifact_results = None, None, {}
        self.artifact_request_id = None
        self.history_job, self.history_callback = None, None
        self.history_rows, self.history_context = [], None
        self.recording_browser, self.recording_context = None, None
        self.removal_preview = None
        self.snapshot_origin = 'live'
        self.title('Aurora — Execution inspector')
        self.configure(bg='#0b1320')
        self.minsize(360, 300)
        fit_popout_window(self, round(980*ui_scale(app)), round(700*ui_scale(app)), app)
        body = ttk.Frame(self, padding=12)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)
        body.rowconfigure(5, weight=2)
        bar = FlowBar(body)
        bar.grid(row=0, column=0, sticky='ew')
        self.refresh_button = bar.add(ttk.Button(bar, text='Load latest export', command=self.load_latest))
        self.collection = tk.StringVar(value='events')
        selector = bar.add(ttk.Combobox(bar, textvariable=self.collection, values=tuple(FIELDS), state='readonly', width=12))
        selector.bind('<<ComboboxSelected>>', self.render)
        self.artifact_button = bar.add(ttk.Button(bar, text='Check request screenshot file', command=self.check_screenshot))
        self.save_button = bar.add(ttk.Button(bar, text='Save snapshot', command=self.save_history))
        bar.add(ttk.Button(bar, text='Saved snapshots', command=self.toggle_history))
        bar.add(ttk.Button(bar, text='Recorded boundaries', command=self.open_recordings))
        bar.add(ttk.Button(bar, text='Close (Esc)', command=self.destroy))
        self.history_area = ttk.Frame(body)
        self.history_area.grid(row=1, column=0, sticky='ew')
        history_bar = FlowBar(self.history_area)
        history_bar.pack(fill='x')
        self.history_selector = history_bar.add(ttk.Combobox(history_bar, state='readonly', width=44))
        self.history_selector.bind('<<ComboboxSelected>>', self.clear_removal_preview)
        self.history_refresh = history_bar.add(ttk.Button(history_bar, text='Refresh saved list', command=lambda: self.start_history({'operation':'list'})))
        self.history_load = history_bar.add(ttk.Button(history_bar, text='Load selected', command=self.load_history))
        self.history_preview_remove = history_bar.add(ttk.Button(history_bar, text='Preview removal', command=self.preview_history_removal))
        self.history_remove = history_bar.add(ttk.Button(history_bar, text='Delete previewed snapshot', command=self.remove_history))
        self.history_cancel = history_bar.add(ttk.Button(history_bar, text='Cancel file operation', command=self.cancel_history))
        self.removal_text = tk.StringVar()
        removal_label = ttk.Label(self.history_area, textvariable=self.removal_text, justify='left', wraplength=800)
        removal_label.pack(fill='x', pady=4)
        bind_label_wrap(removal_label)
        self.history_status = tk.StringVar(value='Manual checkpoints only. Optional boundary recordings use a separate archive.')
        history_label = ttk.Label(self.history_area, textvariable=self.history_status, justify='left', wraplength=800)
        history_label.pack(fill='x', pady=4)
        bind_label_wrap(history_label)
        self.history_area.grid_remove()
        self.summary = tk.StringVar()
        label = ttk.Label(body, textvariable=self.summary, justify='left', wraplength=800)
        label.grid(row=2, column=0, sticky='ew', pady=6)
        bind_label_wrap(label)
        self.notice = tk.StringVar(value=NOTICE)
        label = ttk.Label(body, textvariable=self.notice, style='Muted.TLabel', justify='left', wraplength=800)
        label.grid(row=3, column=0, sticky='ew', pady=(0, 8))
        bind_label_wrap(label)
        area = ttk.Frame(body)
        area.grid(row=4, column=0, sticky='nsew')
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(area, columns=('when', 'stage', 'identity'), show='headings', height=7, selectmode='browse')
        for key, title, width in (('when', 'Local seconds / sequence', 170), ('stage', 'Observed stage / action', 260), ('identity', 'Exact identity', 380)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=round(width*ui_scale(app)), minwidth=90, stretch=key=='identity')
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(area, orient='vertical', command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(area, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Return>', lambda _event: self.details.focus_set())
        area = ttk.Frame(body)
        area.grid(row=5, column=0, sticky='nsew', pady=(8, 0))
        self.details = tk.Text(area, wrap='word', height=12, width=1, bg='#151f30', fg='#e1e9f5', state='disabled', padx=10, pady=8)
        scroll = ttk.Scrollbar(area, command=self.details.yview)
        scroll.pack(side='right', fill='y')
        self.details.configure(yscrollcommand=scroll.set)
        self.details.pack(fill='both', expand=True)
        self.details.bind('<Tab>', lambda _event: (self.details.tk_focusNext().focus_set(), 'break')[1])
        self.details.bind('<Shift-Tab>', lambda _event: (self.details.tk_focusPrev().focus_set(), 'break')[1])
        self.bind('<Escape>', lambda _event: self.destroy())
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.load_latest()
        self.deiconify()

    def load_latest(self):
        if self.recording_browser is not None and not self.recording_browser.cancel():
            return
        self.cancel_history()
        self.clear_removal_preview()
        self.cancel_artifact_check()
        self.artifact_results.clear()
        self.snapshot_origin, self.history_context = 'live', None
        self.recording_context = None
        self.notice.set(NOTICE)
        from aurora2_control_panel import build_state_freshness_text
        state = self.app.state_cache or {}
        snapshot = inspection_snapshot(state)
        task = snapshot['task']
        # Replace as a unit: no merging with an older task or global last frame.
        changed = self.snapshot.get('task', {}).get('task_id') != task.get('task_id')
        self.snapshot = snapshot
        self.summary.set(f"Frozen task: {task.get('task_id', 'none')} · {task.get('status', 'unknown')}\n"
                         f"{build_state_freshness_text(state)} (at load)\n"
                         f"Evicted: {snapshot['retention']} · view omissions: {snapshot['display_omitted']}")
        if changed:
            self.tree.selection_remove(*self.tree.selection())
        self.render()
        self.history_controls()

    def render(self, _event=None):
        collection = self.collection.get()
        self.identities, items = {}, []
        for row in self.snapshot.get('collections', {}).get(collection, []) if self.snapshot.get('available') else []:
            key = {'events': 'sequence', 'commands': 'command_batch_id', 'requests': 'inference_request_id'}[collection]
            identity = row[key]
            iid = collection + ':' + str(identity)
            self.identities[iid] = identity
            stage = (row.get('kind') if collection == 'events' else
                     (row.get('status', 'unknown') + ' · ' + ', '.join(row.get('binding_names', []))) if collection == 'commands' else row.get('phase', 'unknown'))
            when = row.get('observed_at_seconds', row.get('admitted_at', row.get('phase_times', {}).get('prepared', 'unknown')))
            items.append((iid, (str(when), str(stage), str(row.get('identity', identity)))))
        reconcile_tree_rows(self.tree, items)
        if items and not self.tree.selection():
            self.tree.selection_set(items[0][0])
        self.select()

    def select(self, _event=None):
        selection = self.tree.selection()
        identity = self.identities.get(selection[0]) if selection else None
        detail = (inspection_detail(self.snapshot, self.collection.get(), identity) if identity is not None else
                  {'unknown': self.snapshot.get('unavailable_reason', 'No retained records in this collection.')})
        if self.history_context:
            detail['historical_checkpoint'] = self.history_context
        if self.recording_context:
            detail['recorded_boundary'] = self.recording_context
        if self.collection.get() == 'requests' and identity in self.artifact_results:
            detail['local_artifact_check_now'] = self.artifact_results[identity]
        ref = (detail.get('latest_request_in_snapshot') or {}).get('frame_artifact', {})
        self.artifact_button.configure(text='Cancel file check' if self.artifact_check else 'Check request screenshot file',
            state='normal' if self.artifact_check or self.collection.get() == 'requests' and ref.get('artifact_name') else 'disabled')
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', json.dumps(detail, indent=2, ensure_ascii=False))
        self.details.configure(state='disabled')

    def cancel_artifact_check(self):
        if self.artifact_job is not None:
            self.after_cancel(self.artifact_job)
            self.artifact_job = None
        if self.artifact_check is not None:
            self.artifact_results[self.artifact_request_id] = self.artifact_check.cancel()
            self.artifact_check = None
        self.artifact_request_id = None

    def check_screenshot(self):
        if self.artifact_check is not None:
            self.cancel_artifact_check()
            self.select()
            return
        selected = self.tree.selection()
        identity = self.identities.get(selected[0]) if selected else None
        if self.collection.get() != 'requests' or identity is None:
            return
        detail = inspection_detail(self.snapshot, 'requests', identity)
        reference = (detail.get('latest_request_in_snapshot') or {}).get('frame_artifact', {})
        if not reference.get('artifact_name'):
            return
        self.artifact_request_id = identity
        self.artifact_results[identity] = {'status': 'checking'}
        # Local installation root, never a path supplied by an export or request.
        self.artifact_check = ArtifactCheck(Path(__file__).resolve().parent / 'screenshots', reference)
        self.select()
        self.poll_artifact_check()

    def poll_artifact_check(self):
        self.artifact_job = None
        if self.artifact_check is None:
            return
        result = self.artifact_check.poll()
        if result is None:
            self.artifact_job = self.after(50, self.poll_artifact_check)
            return
        self.artifact_results[self.artifact_request_id] = result
        self.artifact_check, self.artifact_request_id = None, None
        self.select()

    def destroy(self):
        if self.recording_browser is not None and not self.recording_browser.destroy():
            return
        self.cancel_history()
        self.cancel_artifact_check()
        super().destroy()

    def open_recordings(self):
        from aurora_recording_browser import RecordingBrowser
        return RecordingBrowser.open(self)

    def load_recorded_boundary(self, result):
        """Replace only the frozen inspection view, never current runtime context."""
        from aurora_recording_store import normalize_record
        record, _, digest = normalize_record(result['record'])
        if result.get('digest') != digest:
            raise ValueError('Recorded boundary digest mismatch.')
        self.cancel_history()
        self.clear_removal_preview()
        self.cancel_artifact_check()
        self.artifact_results.clear()
        self.history_context = None
        self.snapshot_origin = 'recording'
        self.snapshot = copy.deepcopy(record['inspection'])
        self.recording_context = {key:record[key] for key in ('session_id','sequence','kind','identity','task_id',
            'task_event_sequence','observed_at_epoch','source','gaps_before','gap_ranges_omitted','dropped_total_before')}
        self.recording_context.update(digest=digest,integrity='checksum_not_signature')
        self.notice.set('HISTORICAL controller boundary. Current outcome unknown. Linked records reflect this boundary only. No runtime state, actions or model context are restored.')
        self.summary.set(f"RECORDED session {record['session_id']} · sequence {record['sequence']} · {record['kind']}\n"
            f"Task {record['task_id']} · recorded status {self.snapshot['task'].get('status','unknown')} · current outcome unknown\n"
            f"Observed: {self.history_time_label(record['observed_at_epoch'])} · exact identity {record['identity']}")
        self.tree.selection_remove(*self.tree.selection())
        self.render();self.history_controls()

    def history_controls(self):
        busy = self.history_job is not None
        index = self.history_selector.current()
        removable = 0 <= index < len(self.history_rows) and self.history_rows[index].get('status') == 'available'
        self.save_button.configure(state='normal' if not busy and self.snapshot_origin == 'live' and self.snapshot.get('available') else 'disabled')
        self.history_refresh.configure(state='disabled' if busy else 'normal')
        self.history_load.configure(state='normal' if not busy and self.history_rows else 'disabled')
        self.history_cancel.configure(state='normal' if busy else 'disabled')
        self.history_selector.configure(state='disabled' if busy else 'readonly')
        self.history_preview_remove.configure(state='normal' if not busy and removable else 'disabled')
        self.history_remove.configure(state='normal' if not busy and self.removal_preview else 'disabled')

    def clear_removal_preview(self, _event=None):
        self.removal_preview = None
        self.removal_text.set('')
        self.history_controls()

    def preview_history_removal(self):
        index = self.history_selector.current()
        if 0 <= index < len(self.history_rows) and self.history_rows[index].get('status') == 'available':
            self.start_history(dict(operation='preview_remove', checkpoint_ids=[self.history_rows[index]['checkpoint_id']]))

    def remove_history(self):
        preview = self.removal_preview
        index = self.history_selector.current()
        if (not preview or not 0 <= index < len(self.history_rows) or
                preview['checkpoint_ids'] != [self.history_rows[index]['checkpoint_id']]):
            self.clear_removal_preview()
            return
        self.start_history(dict(operation='remove', checkpoint_ids=preview['checkpoint_ids'],
            expected_version=preview['expected_version'], confirm=True))

    def finish_history_removal(self, result):
        # Force refreshed evidence before any further selection or retry.
        self.history_rows = []
        self.history_selector.configure(values=())
        self.history_selector.set('')
        if self.history_context and self.history_context['checkpoint_id'] in result.get('checkpoint_ids', []):
            handle = self.history_context['checkpoint_id']
            self.history_context['saved_file_now'] = 'removed' if handle in result.get('removed', []) else 'unknown; refresh required'
            self.select()

    def toggle_history(self):
        if self.history_area.winfo_manager():
            self.history_area.grid_remove()
        else:
            self.history_area.grid()
            if self.history_job is None:
                self.start_history({'operation':'list'})

    def save_history(self):
        if self.snapshot_origin != 'live' or not self.snapshot.get('available'):
            return
        self.start_history(dict(operation='save', checkpoint_id=uuid.uuid4().hex,
            saved_at_epoch=time.time(), inspection=copy.deepcopy(self.snapshot)))

    def load_history(self):
        index = self.history_selector.current()
        if 0 <= index < len(self.history_rows):
            self.start_history({'operation':'load', 'checkpoint_id':self.history_rows[index]['checkpoint_id']})

    def start_history(self, request):
        if self.history_job is not None:
            return
        if self.recording_browser is not None and not self.recording_browser.cancel():
            return
        self.clear_removal_preview()
        self.history_area.grid()
        self.history_status.set('Working on saved inspection files…')
        self.history_job = HistoryJob(Path(__file__).resolve().parent / 'execution_history', request)
        self.history_controls()
        self.poll_history()

    def cancel_history(self):
        if self.history_callback is not None:
            self.after_cancel(self.history_callback)
            self.history_callback = None
        if self.history_job is not None:
            operation = self.history_job.request.get('operation')
            result = self.history_job.cancel()
            self.history_job = None
            if operation == 'remove':
                self.finish_history_removal(result)
            self.history_status.set(self.history_result_text(result))
            self.history_controls()

    @staticmethod
    def history_time_label(saved):
        try:
            return datetime.datetime.fromtimestamp(saved).astimezone().isoformat(timespec='seconds') if saved else 'time unknown'
        except (ValueError, TypeError, OverflowError, OSError):
            return 'time not displayable (see saved_at_epoch)'

    @staticmethod
    def history_result_text(result):
        status = result.get('status', 'unknown')
        identity = result.get('checkpoint_id') or ''
        if status == 'save_uncertain':
            text = f'Save outcome uncertain for {identity}. Refresh the saved list or load that exact ID before retrying.'
        elif status == 'capacity_reached':
            text = 'History is full (64 checkpoints). Refresh saved list, select a snapshot and Preview removal to free space explicitly.'
        elif status in ('removed', 'removal_partial', 'removal_uncertain'):
            text = (f"Removal: {status.replace('_', ' ')}. Confirmed removed: {', '.join(result.get('removed', [])) or 'none reported'}. "
                    f"Uncertain/inspect: {', '.join(result.get('uncertain', result.get('checkpoint_ids', []) if status == 'removal_uncertain' else [])) or 'none reported'}. "
                    f"Not attempted: {', '.join(result.get('not_attempted', [])) or 'none reported'}. Refresh the saved list before further changes. Loaded view and screenshots stay unchanged.")
        elif status == 'version_conflict':
            text = 'Archive or selection changed since preview. Refresh saved list and preview again; no removal started.'
        else:
            text = f'Saved history: {status.replace("_", " ")} {identity}'.strip()
        if result.get('owned_resources_closed') is False:
            text += ' Helper cleanup is incomplete.'
        return text

    def poll_history(self):
        self.history_callback = None
        if self.history_job is None:
            return
        operation = self.history_job.request.get('operation')
        result = self.history_job.poll()
        if result is None:
            self.history_callback = self.after(50, self.poll_history)
            return
        self.history_job = None
        if operation == 'remove':
            self.finish_history_removal(result)
        status = result.get('status')
        if status == 'listed':
            self.history_rows = result['records']
            labels = []
            for row in self.history_rows:
                saved = row.get('saved_at_epoch')
                when = self.history_time_label(saved)
                labels.append(f"{when} · {row.get('recorded_task_status', row['status'])} · {row['checkpoint_id'][:8]}")
            self.history_selector.configure(values=labels)
            if labels: self.history_selector.current(0)
            else: self.history_selector.set('')
            self.history_status.set(f"{len(labels)} / {result['capacity']} saved · partial files {result['partial_files']} · unrelated files {result['unrelated_files']}. No automatic deletion.")
        elif status == 'removal_preview':
            self.removal_preview = result
            row = result['selected'][0]
            self.removal_text.set(f"PREVIEW — permanently delete saved snapshot {row['checkpoint_id']}\n"
                f"Task {row['task_id']} · saved {self.history_time_label(row['saved_at_epoch'])} · {row['bytes']} bytes\n"
                f"{result['notice']}")
            self.history_status.set('Review the exact snapshot above, then use Delete previewed snapshot. Changing the selection clears this preview.')
        elif status == 'loaded':
            self.cancel_artifact_check()
            self.artifact_results.clear()
            self.snapshot = result['inspection']
            self.snapshot_origin = 'history'
            self.recording_context = None
            self.history_context = {key:result[key] for key in ('checkpoint_id','saved_at_epoch','integrity','notice')}
            self.notice.set(HISTORY_NOTICE)
            task = self.snapshot['task']
            self.summary.set(f"HISTORICAL checkpoint {result['checkpoint_id']}\nTask {task['task_id']} · recorded status {task.get('status','unknown')} · current outcome unknown\nSource export: {self.snapshot.get('source_export',{}).get('timestamp') or 'unknown'} · snapshot links reflect saved export only")
            self.tree.selection_remove(*self.tree.selection())
            self.render()
            self.history_status.set(self.history_result_text(result))
        else:
            self.history_status.set(self.history_result_text(result))
        self.history_controls()
