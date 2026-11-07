"""Explicit history inspection and separately previewed recording retention."""
import copy
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from aurora_recording_service import RecordingJob
from aurora_panel_layout import FlowBar, bind_label_wrap, fit_popout_window, reconcile_tree_rows, ui_scale


class RecordingBrowser(tk.Toplevel):
    @classmethod
    def open(cls, inspector):
        current = getattr(inspector, 'recording_browser', None)
        if current is not None and current.winfo_exists():
            current.deiconify(); current.lift()
            return current
        inspector.recording_browser = cls(inspector)
        return inspector.recording_browser

    def __init__(self, inspector):
        super().__init__(inspector)
        self.withdraw()
        self.inspector = inspector
        self.job = self.callback = None
        self.sessions, self.records = {}, {}
        self.page = None
        self.previous = []
        self.selected_session = None
        self.selected_record = None
        self.closed = False
        self.removal_preview=None;self.uncertain_removal=[]
        self.include_incomplete=tk.BooleanVar(value=False)
        self.title('Aurora — Recorded boundaries')
        self.configure(bg='#0b1320')
        self.minsize(360, 360)
        fit_popout_window(self, round(1000*ui_scale(inspector)), round(760*ui_scale(inspector)), inspector)
        body = ttk.Frame(self, padding=12)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1); body.rowconfigure(4, weight=3)
        bar = FlowBar(body); bar.grid(row=0, column=0, sticky='ew')
        bar.add(ttk.Button(bar, text='Refresh sessions', command=self.refresh_sessions))
        self.browse_button = bar.add(ttk.Button(bar, text='Browse selected session', command=self.browse_session))
        self.cancel_button = bar.add(ttk.Button(bar, text='Cancel operation', command=self.cancel))
        bar.add(ttk.Button(bar, text='Close (Esc)', command=self.destroy))
        self.status = tk.StringVar(value='Refresh to inspect committed metadata. Removal requires a separate preview. Recording remains off unless explicitly enabled.')
        label = ttk.Label(body, textvariable=self.status, wraplength=850, justify='left')
        label.grid(row=1, column=0, sticky='ew', pady=6); bind_label_wrap(label)
        self.session_tree = self.make_tree(body,2,('session','closure','counts'),
            ('Recording session (exact ID)','Closure at published frontier','Committed / accepted / dropped'),(300,280,220),4)
        self.session_tree.bind('<<TreeviewSelect>>', self.session_changed)
        self.session_tree.bind('<Return>', lambda _event:self.browse_session())
        self.session_tree.bind('<Double-1>', lambda _event:self.browse_session())
        bar = FlowBar(body); bar.grid(row=3, column=0, sticky='ew', pady=6)
        self.previous_button = bar.add(ttk.Button(bar, text='Previous page', command=self.previous_page))
        self.next_button = bar.add(ttk.Button(bar, text='Next page', command=self.next_page))
        self.load_button = bar.add(ttk.Button(bar, text='Load boundary in inspector', command=self.load_selected))
        bar.add(ttk.Button(bar, text='Session details / gaps', command=self.toggle_details))
        self.record_tree = self.make_tree(body,4,('sequence','kind','when','identity'),
            ('Sequence','Boundary / availability','Observed local time','Exact boundary identity'),(80,180,210,340),8)
        self.record_tree.bind('<<TreeviewSelect>>', self.record_changed)
        self.record_tree.bind('<Return>', lambda _event:self.load_selected())
        self.record_tree.bind('<Double-1>', lambda _event:self.load_selected())
        self.summary = tk.StringVar(value='Select a session, then Browse. Sequence orders one session; timestamps do not establish order between sessions.')
        label = ttk.Label(body,textvariable=self.summary,wraplength=850,justify='left')
        label.grid(row=5,column=0,sticky='ew',pady=6);bind_label_wrap(label)
        self.detail_area=ttk.Frame(body);self.detail_area.grid(row=6,column=0,sticky='ew')
        self.details=tk.Text(self.detail_area,height=6,width=1,wrap='word',state='disabled',bg='#151f30',fg='#e1e9f5')
        scroll=ttk.Scrollbar(self.detail_area,command=self.details.yview);scroll.pack(side='right',fill='y')
        self.details.configure(yscrollcommand=scroll.set);self.details.pack(fill='both',expand=True)
        self.details.bind('<Tab>',lambda _e:(self.details.tk_focusNext().focus_set(),'break')[1])
        self.details.bind('<Shift-Tab>',lambda _e:(self.details.tk_focusPrev().focus_set(),'break')[1])
        self.detail_area.grid_remove()
        retention=FlowBar(body);retention.grid(row=7,column=0,sticky='ew',pady=6)
        self.preview_button=retention.add(ttk.Button(retention,text='Preview removal',command=self.preview_removal))
        self.remove_button=retention.add(ttk.Button(retention,text='Permanently remove previewed session',command=self.remove_previewed))
        self.reconcile_button=retention.add(ttk.Button(retention,text='Check removal outcome',command=self.check_removal))
        retention.add(ttk.Checkbutton(retention,text='Allow discarding incomplete recording',variable=self.include_incomplete,
                                     command=self.retention_option_changed))
        self.bind('<Escape>',lambda _event:self.destroy());self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.controls();self.deiconify()

    def make_tree(self,body,row,columns,labels,widths,height):
        area=ttk.Frame(body);area.grid(row=row,column=0,sticky='nsew')
        area.columnconfigure(0,weight=1);area.rowconfigure(0,weight=1)
        tree=ttk.Treeview(area,columns=columns,show='headings',height=height,selectmode='browse')
        for key,label,width in zip(columns,labels,widths):
            tree.heading(key,text=label);tree.column(key,width=round(width*ui_scale(self)),minwidth=70)
        tree.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(area,orient='vertical',command=tree.yview);vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(area,orient='horizontal',command=tree.xview);horizontal.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        return tree

    def controls(self):
        busy=self.job is not None
        row=self.sessions.get(self.selected_session,{})
        record=self.records.get(self.selected_record,{})
        for button,enabled in ((self.browse_button,row.get('status')=='available'),
                               (self.previous_button,bool(self.previous)),
                               (self.next_button,self.page is not None and self.page.get('next_after') is not None),
                               (self.load_button,record.get('status')=='available'),
                               (self.preview_button,row.get('status')=='available'),
                               (self.remove_button,self.removal_preview is not None),
                               (self.reconcile_button,bool(self.uncertain_removal))):
            button.configure(state='normal' if enabled and not busy else 'disabled')
        self.cancel_button.configure(state='normal' if busy else 'disabled')

    def clear_page(self):
        self.removal_preview=None
        self.page=None;self.previous=[];self.records={};self.selected_record=None
        reconcile_tree_rows(self.record_tree,[])
        self.set_details({})
        self.summary.set('Browse the selected session to load its ordered boundary index.')

    def session_changed(self,_event=None):
        selected=self.session_tree.selection()
        identity=selected[0] if selected else None
        if identity!=self.selected_session:
            if not self.cancel():return
            self.selected_session=identity;self.clear_page()
        self.controls()

    def record_changed(self,_event=None):
        selected=self.record_tree.selection()
        identity=selected[0] if selected else None
        if identity!=self.selected_record:
            if self.job and self.job.request.get('operation')=='record' and not self.cancel():return
            self.selected_record=identity
        self.controls()

    def refresh_sessions(self):
        if not self.cancel():return
        self.sessions={};self.selected_session=None;self.clear_page()
        reconcile_tree_rows(self.session_tree,[])
        self.start(dict(operation='list'))

    def browse_session(self):
        row=self.sessions.get(self.selected_session,{})
        if row.get('status')!='available':return
        if not self.cancel():return
        self.clear_page()
        self.start(dict(operation='timeline',session_id=row['session_id'],after_sequence=0))

    def next_page(self):
        if self.page and self.page.get('next_after') is not None:
            self.start(dict(operation='timeline',session_id=self.page['session_id'],after_sequence=self.page['next_after'],
                            expected_version=self.page['version']),navigation='next')

    def previous_page(self):
        if self.page and self.previous:
            self.start(dict(operation='timeline',session_id=self.page['session_id'],after_sequence=self.previous[-1],
                            expected_version=self.page['version']),navigation='previous')

    def load_selected(self):
        if self.inspector.history_job is not None:
            self.status.set('Finish or cancel the manual saved-snapshot operation before loading a boundary.')
            return
        row=self.records.get(self.selected_record,{})
        if self.page and row.get('status')=='available':
            self.start(dict(operation='record',session_id=self.page['session_id'],sequence=row['sequence'],expected_digest=row['digest']))

    def start(self,request,*,navigation=None):
        if self.job is not None or self.closed:return
        self.removal_preview=None
        self.navigation=navigation
        self.status.set('Removing only the previewed stored session…' if request['operation']=='remove' else
                        'Reading committed metadata… Current inspector view stays unchanged until an exact boundary loads.')
        try:
            self.job=RecordingJob(Path(__file__).resolve().parent/'execution_recordings',request)
            self.controls();self.poll()
        except Exception:
            if self.cancel():self.status.set('Recording reader unavailable. Current inspector view unchanged.')

    def cancel(self):
        if self.callback is not None:
            self.after_cancel(self.callback);self.callback=None
        if self.job is not None:
            request=copy.deepcopy(self.job.request)
            try:result=self.job.cancel()
            except Exception:result=dict(owned_resources_closed=False)
            if result.get('owned_resources_closed') is False:
                if request.get('operation')=='remove':self.uncertain_removal=request['session_ids']
                self.removal_preview=None
                self.status.set('Helper cleanup incomplete. Retry Cancel operation before closing; removal may be uncertain.')
                self.controls();return False
            self.job=None
            if request.get('operation')=='remove':self.removal_uncertain(request['session_ids'])
            else:self.status.set('Read cancelled; inspector unchanged.')
        if not self.closed:self.controls()
        return True

    def poll(self):
        self.callback=None
        if self.job is None or self.closed:return
        try:result=self.job.poll()
        except Exception:
            if self.cancel():self.status.set('Reader failed; inspector unchanged. Refresh to retry.')
            return
        if result is None:
            self.callback=self.after(50,self.poll);return
        request=copy.deepcopy(self.job.request)
        if result.get('owned_resources_closed') is False:
            self.status.set('Reader cleanup incomplete; inspector unchanged.')
            self.controls();return
        self.job=None
        if request.get('operation')=='remove':
            self.removal_preview=None
            ids=request['session_ids']
            if result.get('status')=='removed' and result.get('session_ids')==ids and result.get('version')==request['expected_version']:
                self.uncertain_removal=[]
                self.clear_removed_rows(ids)
                self.status.set(f"Removed {result['record_count']} stored boundaries ({result['payload_bytes']} payload bytes). "
                                'Loaded inspector view remains; database file size may not shrink. Refresh before further removal.')
                self.set_details(result);self.detail_area.grid()
            elif result.get('status') in ('archive_changed','incomplete_protected','recording_active_or_retention_busy',
                                         'missing_session','confirmation_required','invalid_version','retirement_capacity','unsupported_store'):
                self.status.set('Removal refused: '+result['status'].replace('_',' ')+'. Refresh and preview again.')
            else:self.removal_uncertain(ids)
        elif result.get('status')=='removal_preview':
            if request['session_ids']==[self.selected_session] and request.get('include_incomplete',False)==self.include_incomplete.get():
                self.removal_preview=result
                self.status.set(f"Preview ONLY: {result['session_ids'][0]} · {result['record_count']} boundaries · {result['payload_bytes']} payload bytes. "
                                'Permanently remove previewed session confirms this exact selection. Incomplete history cannot be recovered.')
                self.set_details(result);self.detail_area.grid()
        elif result.get('status')=='removal_status':
            self.clear_removed_rows([row['session_id'] for row in result['sessions'] if row['status']=='retired'])
            self.set_details(result);self.detail_area.grid()
            self.status.set('Removal evidence: '+', '.join(row['session_id']+': '+row['status'] for row in result['sessions'])+
                            '. No removal was retried; refresh sessions before a new preview.')
        elif result.get('status')=='listed':
            items=[];self.sessions={}
            for index,row in enumerate(result['sessions']):
                identity=row.get('session_id') or 'invalid-'+str(index)
                self.sessions[identity]=row
                manifest=row.get('manifest',{})
                counts=f"{row.get('committed_count','?')} / {manifest.get('accepted','?')} / {manifest.get('dropped','?')}"
                closure = row.get('closure','unknown') if row.get('status')=='available' else 'Unavailable: '+row.get('reason',row['status']).replace('_',' ')
                items.append((identity,(row.get('session_id') or 'Invalid identity',closure,counts)))
            reconcile_tree_rows(self.session_tree,items)
            if items:self.session_tree.selection_set(items[0][0])
            self.session_changed()
            self.status.set(f"{len(items)} recorded sessions. Latest published first; not causal order. Select a session and Browse.")
        elif result.get('status')=='timeline' and request['session_id']==self.selected_session:
            if self.navigation=='next' and self.page:self.previous.append(self.page['after_sequence'])
            elif self.navigation=='previous' and self.previous:self.previous.pop()
            self.page=result;self.records={};self.selected_record=None
            items=[]
            for row in result['records']:
                key=str(row['sequence']);self.records[key]=row
                when=self.inspector.history_time_label(row.get('observed_at_epoch'))
                items.append((key,(row['sequence'],row.get('kind',row['status']),when,row.get('identity','unavailable'))))
            reconcile_tree_rows(self.record_tree,items)
            if items:self.record_tree.selection_set(items[0][0])
            self.record_changed()
            coverage=result['coverage'];manifest=result['manifest']
            self.summary.set(f"Session {result['session_id']} · {result['closure']}\n"
                f"{len(items)} boundaries on this page · committed {result['committed_count']} / accepted {manifest['accepted']} · dropped {manifest['dropped']} · unavailable sequences {coverage['unavailable_total']}\n"
                'Sequence is authoritative within this session. Open-session unwritten tails are unknown. See Session details / gaps.')
            self.set_details({key:value for key,value in result.items() if key!='records'})
            self.status.set('Select a boundary and Load. Listing does not change the inspector or runtime.')
        elif result.get('status')=='loaded':
            record=result.get('record',{})
            if (request.get('session_id')==self.selected_session and str(request.get('sequence'))==self.selected_record
                    and record.get('session_id')==request.get('session_id') and record.get('sequence')==request.get('sequence')
                    and result.get('digest')==request.get('expected_digest')):
                try:
                    self.inspector.load_recorded_boundary(result)
                    self.status.set(f"Loaded exact boundary {record['sequence']} in inspector. Historical evidence only; runtime unchanged.")
                except (ValueError,KeyError,TypeError):
                    self.status.set('Invalid recorded boundary; inspector unchanged. Refresh to inspect current evidence.')
            else:self.status.set('Selection changed; returned boundary ignored.')
        else:
            status=result.get('status','unknown')
            self.status.set(f"Recording read: {status.replace('_',' ')}. Inspector unchanged. Refresh sessions / Browse to inspect current evidence.")
            if status=='session_changed':
                self.clear_page()
        self.controls()

    def retention_option_changed(self):
        self.removal_preview=None
        self.controls()

    def preview_removal(self):
        if self.sessions.get(self.selected_session,{}).get('status')!='available':return
        self.start(dict(operation='preview_remove',session_ids=[self.selected_session],
                        include_incomplete=self.include_incomplete.get()))

    def remove_previewed(self):
        preview=self.removal_preview
        if not preview or preview['session_ids']!=[self.selected_session] or preview['include_incomplete']!=self.include_incomplete.get():return
        self.start(dict(operation='remove',session_ids=preview['session_ids'],expected_version=preview['version'],
                        confirm=True,include_incomplete=preview['include_incomplete']))

    def check_removal(self):
        if self.uncertain_removal:self.start(dict(operation='removal_status',session_ids=self.uncertain_removal))

    def removal_uncertain(self,ids):
        self.uncertain_removal=list(ids);self.removal_preview=None
        self.status.set('Removal outcome uncertain. Use Check removal outcome; no deletion is retried automatically. Inspector unchanged.')

    def clear_removed_rows(self,ids):
        for identity in ids:
            self.sessions.pop(identity,None)
            if self.session_tree.exists(identity):self.session_tree.delete(identity)
        if self.selected_session in ids:self.selected_session=None;self.clear_page()
        # A frozen, already loaded historical view remains useful even after storage removal.
        if self.inspector.recording_context and self.inspector.recording_context.get('session_id') in ids:
            self.inspector.recording_context['stored_session_now']='removed; loaded historical view retained'

    def set_details(self,value):
        self.details.configure(state='normal');self.details.delete('1.0','end')
        self.details.insert('1.0',json.dumps(value,indent=2));self.details.configure(state='disabled')

    def toggle_details(self):
        if self.detail_area.winfo_manager():self.detail_area.grid_remove()
        else:self.detail_area.grid()

    def destroy(self):
        if self.closed:return True
        if not self.cancel():return False
        self.closed=True
        self.inspector.recording_browser=None
        super().destroy()
        return True
