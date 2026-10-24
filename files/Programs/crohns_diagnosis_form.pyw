"""Crohn's first-diagnosis evidence organizer. Python 3.10+, standard library only."""
import json
import math
import tempfile
import webbrowser
from pathlib import Path
from datetime import date
from html import escape
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

VERSION = '1.0'
TRI = ['Unknown / not assessed', 'Present', 'Absent']
STATUS = ['Unknown / not assessed', 'Performed', 'Not performed', 'Pending']
REFS = [
 ('ECCO–ESGAR–ESP–IBUS diagnostics guideline (2025)', 'https://doi.org/10.1093/ecco-jcc/jjaf106'),
 ('BSG guidelines on inflammatory bowel disease (2025)', 'https://doi.org/10.1136/gutjnl-2024-334395'),
 ('ACG Crohn’s disease guideline (2025)', 'https://doi.org/10.14309/ajg.0000000000003465')]
# Each field: key, label, choices (None means free text).
GROUPS = [
 ('Patient', [('patient','Patient / study ID (optional)',None),('clinician','Clinician (optional)',None),('date','Assessment date YYYY-MM-DD',None),('age','Age in years (optional)',None),('duration','Symptom duration / course',None),('notes','Clinical notes / prior steroids or other treatment',None)]),
 ('Symptoms', [(k,l,TRI) for k,l in [
 ('diarrhea','Persistent diarrhea'),('nocturnal','Nocturnal bowel movements'),('pain','Persistent abdominal pain'),('weight','Unintentional weight loss'),('growth','Growth failure / delayed puberty'),('blood','Visible rectal bleeding'),('family','First-degree relative with IBD'),('perianal','Complex / recurrent perianal fistula'),('extra','Oral ulcers / joint, eye or skin manifestations')]]),
 ('Urgent features', [(k,l,TRI) for k,l in [
 ('severe','Severe or rapidly worsening abdominal pain'),('obstruction','Persistent vomiting with distension / inability to pass stool or gas'),('sepsis','Fever with marked illness / suspected sepsis'),('bleeding','Heavy bleeding, fainting or severe dehydration'),('pa_abscess','Painful perianal swelling / suspected abscess')]]),
 ('Laboratory', [('fc','Fecal calprotectin (µg/g; blank = unknown)',None),('fc_flag','Calprotectin interpretation using local lab / pathway',['Unknown / not assessed','Elevated','Borderline','Within reference range']),('crp','CRP (mg/L; blank = unknown)',None),('hb','Hemoglobin (g/dL; blank = unknown)',None),('platelets','Platelets (×10⁹/L; blank = unknown)',None),('albumin','Albumin (g/L; blank = unknown)',None)] + [(k,l,TRI) for k,l in [('inflammation','CRP or ESR elevated for local reference'),('anemia','Anemia / iron deficiency confirmed'),('thromb','Thrombocytosis confirmed'),('lowalbumin','Low albumin confirmed')]]),
 ('Endoscopy', [('endo_status','Ileocolonoscopy status',STATUS),('ileum','Terminal ileum examined adequately',TRI),('biopsy_sample','Segmental biopsies obtained',TRI)] + [(k,l,TRI) for k,l in [('long_ulcers','Deep longitudinal / serpiginous ulcers'),('cobble','Cobblestoning'),('skip','Discontinuous / skip inflammation'),('ileitis','Terminal ileal ulceration'),('aphthae','Aphthous ulcers'),('endo_stricture','Endoscopic stricture'),('uc_pattern','Continuous rectum-based colitis / UC-like pattern')]] + [('endo_notes','Extent / examination limitations / date',None)]),
 ('Histology', [('histo_status','Biopsy histology status',STATUS)] + [(k,l,TRI) for k,l in [('chronic','Patchy chronic inflammation'),('distortion','Focal crypt architectural distortion'),('granuloma','Noncaseating granulomas NOT related to crypt rupture'),('other_path','Pathology suggests an alternative diagnosis')]] + [('path_notes','Pathologist conclusion / site / date',None)]),
 ('Imaging', [('image_status','Small-bowel imaging status',STATUS),('modality','Imaging method',['Unknown / not assessed','MR enterography','Intestinal ultrasound','CT enterography','Other'])] + [(k,l,TRI) for k,l in [('segmental','Segmental / asymmetric bowel inflammation'),('wall','Wall thickening / edema / hyperenhancement'),('stricture','Stricture with upstream dilation'),('fistula','Enteric fistula / penetrating sinus tract'),('abscess','Intra-abdominal abscess'),('fat','Comb sign / inflammatory mesenteric fat')]] + [('image_notes','Location / extent / limitations / date',None)]),
 ('Other causes', [('stool','Enteric pathogen testing',['Unknown / not assessed','Negative','Positive','Pending']),('cdiff','C. difficile testing',['Unknown / not assessed','Negative','Positive','Pending'])] + [(k,l,TRI) for k,l in [('nsaid','Recent / ongoing NSAID exposure'),('tb','TB exposure / epidemiological or clinical concern'),('behcet','Features suggesting Behçet’s disease'),('other','Other plausible diagnosis identified')]] + [('mimic_notes','Alternative diagnoses / relevant tests and results',None)])]
FIELDS = {k:(label,options) for _,fs in GROUPS for k,label,options in fs}
NUMBERS = {'age':(0,120),'fc':(0,100000),'crp':(0,2000),'hb':(0.1,30),'platelets':(0,5000),'albumin':(0,100)}


def defaults():
    return {k: (options[0] if options else date.today().isoformat() if k=='date' else '') for k,(_,options) in FIELDS.items()}


def validate(d):
    for k,(label,options) in FIELDS.items():
        v=d.get(k,'')
        if not isinstance(v,str): raise ValueError(f'{label}: invalid value type.')
        if options and v not in options: raise ValueError(f'{label}: select an available option.')
        if k in NUMBERS and v.strip():
            try: n=float(v)
            except ValueError: raise ValueError(f'{label}: enter a number.')
            lo,hi=NUMBERS[k]
            if not math.isfinite(n) or not lo<=n<=hi: raise ValueError(f'{label}: check units and value ({lo}–{hi}).')
    if d.get('date'):
        try: date.fromisoformat(d['date'])
        except ValueError: raise ValueError('Use YYYY-MM-DD for the assessment date.')
    # A procedure finding cannot exist in this form without a completed procedure.
    for status,keys in [('endo_status',['ileum','biopsy_sample','long_ulcers','cobble','skip','ileitis','aphthae','endo_stricture','uc_pattern']),('histo_status',['chronic','distortion','granuloma','other_path']),('image_status',['segmental','wall','stricture','fistula','abscess','fat'])]:
        if d[status]!='Performed' and any(d[k] in ('Present','Absent') for k in keys):
            raise ValueError(f'{FIELDS[status][0]} must be Performed before recording its findings. Otherwise leave findings Unknown.')


def assess(d):
    validate(d)
    yes=lambda k:d.get(k)=='Present'
    urgent=[]; support=[]; alternatives=[]; gaps=[]; steps=[]
    for k in ['severe','obstruction','sepsis','bleeding','pa_abscess','abscess']:
        if yes(k): urgent.append(FIELDS[k][0])
    if urgent: steps.append('Urgent in-person assessment: emergency care for severe pain, obstruction, heavy bleeding/fainting, dehydration or systemic illness; prompt same-day assessment for suspected abscess. Do not delay for this form or routine testing.')
    for k in ['long_ulcers','cobble','skip','ileitis','aphthae','endo_stricture','chronic','distortion','granuloma','segmental','wall','stricture','fistula','fat','perianal']:
        if yes(k): support.append(FIELDS[k][0])
    if yes('granuloma'): alternatives.append('Granulomas require review for infection (including TB when relevant) and other granulomatous causes; they do not prove Crohn’s.')
    for k in ['diarrhea','nocturnal','pain','weight','growth','blood','family','extra','inflammation','anemia','thromb','lowalbumin']:
        if yes(k): support.append(FIELDS[k][0]+' — supportive / nonspecific')
    if d['fc_flag'] in ('Elevated','Borderline'): support.append('Calprotectin '+d['fc_flag'].lower()+': intestinal inflammation is possible; this does not identify Crohn’s specifically.')
    if d['fc_flag']=='Within reference range': steps.append('Calprotectin within reference range does not exclude Crohn’s when suspicion persists, particularly limited small-bowel disease.')
    if d['fc'] and d['fc_flag']=='Unknown / not assessed': gaps.append('Calprotectin value entered without local-laboratory interpretation; no universal diagnostic cutoff applied.')
    for k in ['stool','cdiff']:
        if d[k]=='Positive': alternatives.append(FIELDS[k][0]+': positive. Review organism, clinical significance and possible coexisting IBD before attributing findings to Crohn’s.')
        elif d[k] in ('Unknown / not assessed','Pending'): gaps.append(FIELDS[k][0]+': '+d[k])
    for k in ['nsaid','tb','behcet','other','other_path','uc_pattern']:
        if yes(k): alternatives.append(FIELDS[k][0]+': requires clinician review.')
    if yes('tb'): steps.append('Assess intestinal TB where clinically indicated; a blood TB test alone cannot establish or exclude intestinal TB.')
    for k in ['endo_status','histo_status','image_status']:
        if d[k]!='Performed': gaps.append(FIELDS[k][0]+': '+d[k])
    if d['endo_status']=='Performed':
        for k in ['ileum','biopsy_sample']:
            if not yes(k): gaps.append(FIELDS[k][0]+': '+d[k])
    if d['endo_status']!='Performed' or not yes('biopsy_sample'): steps.append('For persistent suspicion of IBD, specialist-directed ileocolonoscopy with segmental biopsies is a core investigation. Acute severe colitis may require a limited examination instead.')
    if d['image_status']!='Performed': steps.append('Consider small-bowel assessment with MR enterography and/or intestinal ultrasound as part of the initial work-up; choose modality with the treating team.')
    if yes('perianal') or yes('pa_abscess'): steps.append('Consider pelvic MRI and colorectal/IBD specialist assessment for perianal disease.')
    if d['age'] and float(d['age'])<18: steps.append('Pediatric patient: use a pediatric IBD pathway; this adult-oriented organizer is not a pediatric diagnostic algorithm.')
    steps.append('If initial examinations are inconclusive but suspicion persists, review test quality, pathology and small-bowel evaluation. Capsule endoscopy is a specialist option only after assessing retention/stricture risk.')
    if yes('stricture') or yes('obstruction') or yes('endo_stricture'): steps.append('Possible obstruction/stricture: do not proceed directly to capsule endoscopy; specialist assessment of patency/retention risk is required.')
    unknown=[label for k,(label,opts) in FIELDS.items() if (opts and d[k] in ('Unknown / not assessed','Pending'))]
    sections=[('Assessment','Evidence organizer only. No probability, diagnostic score or automatic diagnosis is calculated. Findings below require clinician interpretation; absence of recorded evidence does not exclude Crohn’s.'),('Urgent findings',urgent or ['No urgent features recorded as present. Unassessed features and clinical deterioration still require review.']),('Recorded supportive findings',support or ['No supportive findings recorded. This may reflect missing investigations.']),('Alternative explanations / cautions',alternatives or ['No alternative explanation recorded; mimics have not automatically been excluded.']),('Priority information gaps',gaps or ['No procedural status gaps identified; adequacy and complete results still require clinical review.']),('Suggested next steps',steps),('Unassessed items',unknown or ['None marked unknown or pending.']),('Clinician conclusion',d.get('conclusion','').strip() or 'Not entered. Final diagnosis and decisions remain with the treating clinician.')]
    return sections


def text_report(d):
    return '\n\n'.join(title+'\n'+(body if isinstance(body,str) else '\n'.join('• '+x for x in body)) for title,body in assess(d))


def html_report(d):
    e=escape
    blocks=[]
    for title,body in assess(d):
        body='<p>'+e(body)+'</p>' if isinstance(body,str) else '<ul>'+''.join('<li>'+e(x)+'</li>' for x in body)+'</ul>'
        blocks.append('<section><h2>'+e(title)+'</h2>'+body+'</section>')
    inputs=''.join('<h2>'+e(group)+'</h2><table>'+''.join('<tr><th>'+e(label)+'</th><td>'+e(d.get(k,'') or 'Not entered')+'</td></tr>' for k,label,_ in fs)+'</table>' for group,fs in GROUPS)
    refs=''.join('<li>'+e(title)+' — <a href="'+e(url)+'">'+e(url)+'</a></li>' for title,url in REFS)
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Crohn’s first-diagnosis assessment</title><style>body{font:15px Arial,sans-serif;line-height:1.5;max-width:950px;margin:32px auto;color:#183047;padding:0 20px}h1{font-size:25px}h2{font-size:18px;color:#166b72;margin-top:24px}li{margin:7px 0}th,td{padding:7px;border-bottom:1px solid #dce4e9;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{width:55%}table{width:100%;border-collapse:collapse}h2{break-after:avoid}tr{break-inside:avoid}a{overflow-wrap:anywhere}@media print{body{font-size:10pt;margin:0;max-width:none}.noprint{display:none}}@page{size:A4;margin:16mm}</style><body><h1>Crohn’s disease • first-diagnosis assessment</h1><p>Patient/study ID: '+e(d['patient'] or 'Not entered')+' | Date: '+e(d['date'])+' | Version '+VERSION+'</p><p class="noprint">Press Ctrl+P (Mac: Command+P) to print or select Save as PDF. This report is stored locally.</p>'+''.join(blocks)+'<h1>Entered information</h1>'+inputs+'<h2>References and method</h2><p>Guideline-informed checklist; the software rules have not been clinically validated. No numeric weights or likelihood ratios are combined. Sources reviewed 9 October 2026.</p><ul>'+refs+'</ul></body></html>'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Crohn’s • First-diagnosis assessment — v'+VERSION)
        self.geometry('1180x820'); self.minsize(880,620)
        self.temp=tempfile.TemporaryDirectory(prefix='crohns_assessment_')
        self.vars={k:tk.StringVar(value=v) for k,v in defaults().items()}
        self.vars['conclusion']=tk.StringVar()
        ttk.Label(self,text='Crohn’s disease | First-diagnosis assessment',font=('Segoe UI',19,'bold')).pack(anchor='w',padx=18,pady=(14,3))
        tk.Label(self,text='Clinician evidence organizer | No diagnostic percentage | Unknown is not a negative result',wraplength=1000).pack(anchor='w',padx=18,pady=(0,10))
        tk.Label(self,text='This software cannot replace a physician. It is made for educational purposes only. The author decline any responsibility, if it is used by any one, for medical purposes.',fg='red',wraplength=1000).pack(anchor='w',padx=18,pady=(0,10))
        tk.Label(self,text='Making the diagnosis of any disease is the responsibility of your physician only. You cannot use it, in any way, to make the diagnosis of your disease or your symptoms.',fg='red',wraplength=1000).pack(anchor='w',padx=18,pady=(0,10))        
        tk.Label(self,text='It is not a medical advisor at all.',fg='red',wraplength=1000).pack(anchor='w',padx=18,pady=(0,10))         
        bar=ttk.Frame(self); bar.pack(fill='x',padx=15,pady=5)
        for label,fn in [('Review assessment',self.review),('Print',lambda:self.export('print')),('Save as PDF',lambda:self.export('pdf')),('Save report HTML',lambda:self.export('html')),('Save case',self.save),('Load case',self.load),('New case',self.clear)]:
            ttk.Button(bar,text=label,command=fn).pack(side='left',padx=3)
        self.book=ttk.Notebook(self); self.book.pack(fill='both',expand=True,padx=15,pady=10)
        for name,fields in GROUPS:
            page=ttk.Frame(self.book); self.book.add(page,text=name)
            canvas=tk.Canvas(page,highlightthickness=0); scroll=ttk.Scrollbar(page,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            inner=ttk.Frame(canvas,padding=18);win=canvas.create_window((0,0),window=inner,anchor='nw')
            inner.bind('<Configure>',lambda ev,c=canvas:c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>',lambda ev,c=canvas,w=win:c.itemconfigure(w,width=ev.width))
            inner.columnconfigure(1,weight=1)
            for row,(k,label,options) in enumerate(fields):
                ttk.Label(inner,text=label,wraplength=450,justify='left').grid(row=row,column=0,sticky='w',padx=(0,20),pady=9)
                widget=ttk.Combobox(inner,textvariable=self.vars[k],values=options,state='readonly',width=35) if options else ttk.Entry(inner,textvariable=self.vars[k],width=45)
                widget.grid(row=row,column=1,sticky='ew',pady=9)
            if name=='Laboratory': ttk.Label(inner,text='Use original laboratory units shown above. Values are recorded, not automatically classified.\nSelect interpretations using the local laboratory ranges; blank values remain unknown.',wraplength=900).grid(row=len(fields),column=0,columnspan=2,sticky='w',pady=15)
        self.result_page=ttk.Frame(self.book);self.book.add(self.result_page,text='Assessment')
        self.result=ScrolledText(self.result_page,wrap='word',font=('Segoe UI',11),padx=15,pady=15,state='disabled');self.result.pack(fill='both',expand=True)
        ttk.Label(self.result_page,text='Clinician conclusion / plan (included in exports):').pack(anchor='w',padx=10)
        ttk.Entry(self.result_page,textvariable=self.vars['conclusion']).pack(fill='x',padx=10,pady=8)
        refs=ttk.Frame(self.book,padding=20);self.book.add(refs,text='Help / references')
        helptext='Complete available fields; leave unknown findings unchanged. Set procedure status to Performed before recording its findings.\n\nReview assessment regenerates the report. Exports always use current entries. Print and PDF use your browser print dialog; no PDF library is needed.\n\nSave case creates a plain, unencrypted JSON file. Reports also contain your entries. Use a study ID where appropriate and protect saved files. No patient data is transmitted by this application.\n\nThis checklist supports clinical review. It does not diagnose, exclude Crohn’s, prescribe treatment or compute risk categories. Urgent prompts are not an exhaustive triage system.\n\nWindows: py -3.12 crohns_diagnosis_form.py\n\nReferences (reviewed 9 October 2026):\n'+ '\n\n'.join(t+'\n'+u for t,u in REFS)
        txt=ScrolledText(refs,wrap='word',font=('Segoe UI',11));txt.pack(fill='both',expand=True);txt.insert('1.0',helptext);txt.configure(state='disabled')
        self.protocol('WM_DELETE_WINDOW',self.close)
    def data(self): return {k:v.get() for k,v in self.vars.items()}
    def checked(self):
        d=self.data()
        try: validate(d);return d
        except ValueError as exc: messagebox.showerror('Please check entries',str(exc),parent=self);return None
    def review(self):
        d=self.checked()
        if d is None:return
        self.result.configure(state='normal');self.result.delete('1.0','end');self.result.insert('1.0',text_report(d));self.result.configure(state='disabled');self.book.select(self.result_page)
    def export(self,kind):
        d=self.checked()
        if d is None:return
        try:
            if kind=='html':
                name=filedialog.asksaveasfilename(defaultextension='.html',initialfile='Crohns_assessment.html',filetypes=[('HTML report','*.html')])
                if not name:return
                path=Path(name)
            else:
                import uuid
                path=Path(self.temp.name)/(uuid.uuid4().hex+'.html')
            path.write_text(html_report(d),encoding='utf-8')
            if not webbrowser.open(path.resolve().as_uri()): messagebox.showinfo('Report created','Open this report manually:\n'+str(path))
            else: messagebox.showinfo('Report ready','In your browser press Ctrl+P (Mac: Command+P), then '+('choose Save as PDF / Microsoft Print to PDF.' if kind=='pdf' else 'choose your printer or Save as PDF.')+'\nKeep this application open until printing is complete.')
        except OSError as exc:messagebox.showerror('Export failed',str(exc))
    def save(self):
        # Incomplete drafts may be saved, including procedural inconsistencies.
        name=filedialog.asksaveasfilename(defaultextension='.json',initialfile='Crohns_case.json',filetypes=[('Case file','*.json')])
        if name:
            try:Path(name).write_text(json.dumps({'app':'crohns-first-diagnosis','version':VERSION,'data':self.data()},ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as exc:messagebox.showerror('Save failed',str(exc))
    def load(self):
        name=filedialog.askopenfilename(filetypes=[('Case file','*.json')])
        if not name:return
        if not messagebox.askyesno('Replace current entries?','Loading replaces current entries. Continue?'):return
        try:
            obj=json.loads(Path(name).read_text(encoding='utf-8'))
            if obj.get('app')!='crohns-first-diagnosis' or obj.get('version')!=VERSION or not isinstance(obj.get('data'),dict):raise ValueError('Unsupported case file.')
            d=defaults();d['conclusion']=''
            for k,v in obj['data'].items():
                if k in d:
                    if not isinstance(v,str):raise ValueError('Invalid case value.')
                    if k in FIELDS and FIELDS[k][1] and v not in FIELDS[k][1]:raise ValueError('Invalid choice in case file.')
                    d[k]=v
            for k,v in d.items():self.vars[k].set(v)
            self.reset_result();self.book.select(0)
        except (OSError,ValueError,AttributeError) as exc:messagebox.showerror('Load failed',str(exc))
    def reset_result(self):
        self.result.configure(state='normal');self.result.delete('1.0','end');self.result.configure(state='disabled')
    def clear(self):
        if messagebox.askyesno('New case','Discard current entries? Save the case first if needed.'):
            for k,v in {**defaults(),'conclusion':''}.items():self.vars[k].set(v)
            self.reset_result();self.book.select(0)
    def close(self):
        if messagebox.askyesno('Close','Close application? Unsaved case entries and temporary reports will be discarded.'):
            self.temp.cleanup();self.destroy()

if __name__=='__main__':
    App().mainloop()
