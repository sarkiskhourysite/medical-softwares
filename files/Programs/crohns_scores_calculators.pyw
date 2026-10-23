"""Crohn's disease calculators. Python 3.10+, PySide6. Run this file to open.
Offline calculation aid, not a validated medical device. See README.md.
"""
import sys
import math
from datetime import datetime
from html import escape
from pathlib import Path
try:
    from PySide6.QtCore import Qt, QDate
    from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout
    from PySide6.QtCore import QMarginsF
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton,
        QTabWidget, QScrollArea, QGroupBox, QTextBrowser, QFileDialog,
        QMessageBox, QDateEdit, QDialog)
    from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
except ImportError:
    raise SystemExit('Install the dependency first: python -m pip install PySide6')

VERSION = '1.0 - 2026-10-05'
NOTICE = ('Calculation aid for trained clinical use. Scores do not diagnose disease, '
          'establish mucosal healing, or independently determine treatment. '
          'Review the inputs and clinical context before using a report.')
YES = [('No', 0), ('Yes', 1)]
PAIN = [(f'{i} - {s}', i) for i,s in enumerate(['None','Mild','Moderate','Severe'])]
WELL = [(f'{i} - {s}', i) for i,s in enumerate(['Very well','Slightly unwell','Poor','Very poor','Terrible'])]
REFS = {
'CDAI': [('Best et al. Gastroenterology 1976;70:439-444.', 'https://pubmed.ncbi.nlm.nih.gov/1248701/'),
         ('IG-IBD: CDAI scoring conventions.', 'https://www.igibdscores.it/en/info-cdai.php')],
'HBI': [('Harvey & Bradshaw. Lancet 1980;1:514. Scoring guidance:', 'https://www.igibdscores.it/en/info-hbi.php')],
'SES-CD': [('Daperno et al. Gastrointest Endosc 2004;60:505-512.', 'https://pubmed.ncbi.nlm.nih.gov/15472670/'),
           ('IG-IBD: SES-CD scoring guidance.', 'https://www.igibdscores.it/en/info-sescd.php')],
'Rutgeerts': [('Rutgeerts et al. Gastroenterology 1990;99:956-963.', 'https://pubmed.ncbi.nlm.nih.gov/2394349/'),
             ('Modified i2a versus i2b individual-patient meta-analysis.', 'https://pubmed.ncbi.nlm.nih.gov/36124813/')],
'PRO2': [('Khanna et al. Aliment Pharmacol Ther 2015;41:77-86.', 'https://pubmed.ncbi.nlm.nih.gov/25348809/'),
         ('SF/AP trial remission definition and baseline restrictions.', 'https://pubmed.ncbi.nlm.nih.gov/31644790/')],
'MaRIA': [('Rimola et al. Inflamm Bowel Dis 2011;17:1759-1767.', 'https://pubmed.ncbi.nlm.nih.gov/21744431/')],
'sMaRIA': [('Ordas et al. Gastroenterology 2019;157:432-439.e1.', 'https://pubmed.ncbi.nlm.nih.gov/30953614/'),
           ('External validation: alternative severe cutoff reported.', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7724527/')]
}

def number(s, label, low=0, high=float('inf'), integer=False):
    if not str(s).strip():
        raise ValueError(f'{label}: enter a value (use 0 when absent).')
    try: n = float(s)
    except (ValueError, TypeError): raise ValueError(f'{label}: enter a valid number.')
    if not math.isfinite(n) or not low <= n <= high or (integer and not n.is_integer()):
        raise ValueError(f'{label}: invalid value or range. Check units and whole-number requirements.')
    return int(n) if integer else n

def cdai(stools, pain, well, comp, drug, mass, ref, hct, weight, standard):
    points = [2*sum(stools),5*sum(pain),7*sum(well),20*sum(comp),30*drug,
              10*mass,6*(ref-hct),100*(standard-weight)/standard]
    total = sum(points)
    band = 'Clinical remission' if total<150 else 'Mild activity' if total<220 else 'Moderate-severe activity' if total<=450 else 'Severe activity'
    return total, band, points

def hbi(well,pain,stools,mass,comp):
    total = well+pain+stools+mass+sum(comp)
    return total, ('Clinical remission' if total<5 else 'Mild activity' if total<8 else 'Moderate activity' if total<=16 else 'Severe activity')

def maria(wall,rce,edema,ulcers): return 1.5*wall+0.02*rce+5*edema+10*ulcers

def smaria(wall,edema,fat,ulcers): return int(wall>3)+edema+fat+2*ulcers

def pro2(stools,pain):
    sf, ap = sum(stools)/7, sum(pain)/7
    return sf, ap, 2*sf+5*ap

def fmt(v): return f'{v:.3f}'.rstrip('0').rstrip('.') if isinstance(v,float) else str(v)

def para(s): return '<p>'+escape(str(s)).replace('\n','<br>')+'</p>'

def table(rows):
    return '<table width="100%" border="1" cellspacing="0" cellpadding="3">'+''.join('<tr>'+''.join('<td>'+escape(str(c))+'</td>' for c in row)+'</tr>' for row in rows)+'</table>'

class ScoreTab(QWidget):
    def __init__(self, app, title, intro, guidance):
        super().__init__()
        self.app, self.title, self.guidance = app, title, guidance
        self.fields = {}; self.labels = {}; self.sections = {}; self.ready = False
        layout = QVBoxLayout(self)
        heading = QLabel(title); heading.setObjectName('heading'); layout.addWidget(heading)
        label = QLabel(intro); label.setWordWrap(True); layout.addWidget(label)
        body = QHBoxLayout(); layout.addLayout(body,1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.formwidget = QWidget(); self.formlayout=QVBoxLayout(self.formwidget)
        scroll.setWidget(self.formwidget); body.addWidget(scroll,3)
        self.result = QTextBrowser(); self.result.setOpenExternalLinks(True); self.result.setMinimumWidth(310)
        body.addWidget(self.result,2)
        actions = QHBoxLayout(); layout.addLayout(actions)
        for name, fn in [('Calculate',self.update_result),('Print preview',self.preview),('Print result',self.print_result),('Save PDF',self.save_pdf),('Clear this tab',self.clear)]:
            b=QPushButton(name); b.clicked.connect(fn); actions.addWidget(b)
        self.build()
        self.add_section('Assessment notes')
        self.entry('notes','Notes / limitations (optional)')
        self.formlayout.addStretch(); self.ready=True; self.update_result()

    def add_section(self,title):
        g=QGroupBox(title); f=QFormLayout(g); f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.formlayout.addWidget(g); self.current=f

    def entry(self,key,label,options=None):
        if options is None:
            w=QLineEdit(); w.setPlaceholderText('Enter value'); w.textChanged.connect(self.update_result)
        else:
            w=QComboBox(); w.addItem('Select...',None)
            for text,value in options: w.addItem(text,value)
            w.currentIndexChanged.connect(self.update_result)
        w.setAccessibleName(label); self.current.addRow(label,w)
        self.fields[key]=w; self.labels[key]=label
        return w

    def choice(self,k):
        v=self.fields[k].currentData()
        if v is None: raise ValueError(self.labels[k]+': select an option.')
        return v

    def num(self,k,low=0,high=float('inf'),integer=False):
        return number(self.fields[k].text(),self.labels[k],low,high,integer)

    def selected(self,k): return self.fields[k].currentData()

    def build(self): pass
    def calculate(self): return '', ''

    def update_result(self,*args):
        if not self.ready:return
        try:
            self.summary,self.details=self.calculate(); self.valid=True
        except ValueError as exc:
            self.summary='INCOMPLETE / NOT SCORED'; self.details=para(exc); self.valid=False
        self.result.setHtml('<h2>'+escape(self.summary)+'</h2>'+self.details+para(self.guidance)+self.references())

    def references(self):
        return '<h3>References</h3>'+''.join('<p>'+escape(t)+'<br><a href="'+u+'">'+u+'</a></p>' for t,u in REFS[self.title])

    def report_html(self):
        self.update_result()
        rows=[['Parameter','Entered value']]
        for k,w in self.fields.items():
            if not w.isEnabled(): continue
            value=w.currentText() if isinstance(w,QComboBox) else w.text()
            rows.append([self.labels[k],value or 'Not entered'])
        return ('<html><head><style>body{font-family:Arial;font-size:9pt;color:#183342} '
                'h1,h2{color:#0f6772} p{margin-top:5px;margin-bottom:5px} td{vertical-align:top} </style></head><body>'
                '<h1>Crohn\'s disease | '+escape(self.title)+'</h1>'+
                para('Patient / study ID: '+(self.app.patient.text() or 'Not entered'))+
                para('Assessment date: '+self.app.date.date().toString('yyyy-MM-dd')+' | Clinician: '+(self.app.clinician.text() or 'Not entered'))+
                '<h2>'+escape(self.summary)+'</h2>'+self.details+para(self.guidance)+table(rows)+self.references()+para(NOTICE)+
                para('Generated '+datetime.now().strftime('%Y-%m-%d %H:%M')+' | Application '+VERSION)+'</body></html>')

    def document(self, printer=None):
        d=QTextDocument(); d.setHtml(self.report_html())
        if printer is not None:
            d.setPageSize(printer.pageRect(QPrinter.Unit.DevicePixel).size()); d.setDocumentMargin(0)
        return d

    def printer(self):
        p=QPrinter(QPrinter.PrinterMode.ScreenResolution)
        p.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        p.setPageMargins(QMarginsF(15,15,15,15),QPageLayout.Unit.Millimeter)
        return p

    def export_pdf(self,path):
        p=self.printer(); p.setOutputFormat(QPrinter.OutputFormat.PdfFormat); p.setOutputFileName(str(path))
        p.setDocName(self.title+' - Crohn assessment'); self.document(p).print_(p)
        if not Path(path).is_file() or Path(path).stat().st_size==0: raise OSError('PDF was not created.')

    def save_pdf(self):
        path,_=QFileDialog.getSaveFileName(self,'Save result as PDF',self.title.replace('/','_')+'_Report.pdf','PDF (*.pdf)')
        if not path:return
        if not path.lower().endswith('.pdf'):path+='.pdf'
        try:self.export_pdf(path)
        except Exception as exc:QMessageBox.critical(self,'PDF export failed',str(exc));return
        QMessageBox.information(self,'Saved','Report saved to:\n'+path)

    def preview(self):
        p=self.printer(); dlg=QPrintPreviewDialog(p,self); doc=self.document(p)
        dlg.paintRequested.connect(doc.print_); dlg.resize(950,750); dlg.exec()

    def print_result(self):
        p=self.printer(); dialog=QPrintDialog(p,self)
        if dialog.exec()==QDialog.DialogCode.Accepted: self.document(p).print_(p)

    def clear(self):
        if QMessageBox.question(self,'Clear tab','Clear all inputs on this tab?')!=QMessageBox.StandardButton.Yes:return
        self.ready=False
        for w in self.fields.values():
            if isinstance(w,QComboBox):w.setCurrentIndex(0)
            else:w.clear()
        self.ready=True; self.update_result()

    def diary(self,well=False):
        for i in range(7):
            self.add_section(f'Day {i+1}')
            self.entry(f's{i}',f'Day {i+1}: liquid / very soft stools (whole number)')
            self.entry(f'p{i}',f'Day {i+1}: abdominal pain',PAIN)
            if well:self.entry(f'w{i}',f'Day {i+1}: well-being',WELL)

    def diary_values(self,well=False):
        values=([self.num(f's{i}',integer=True) for i in range(7)],[self.choice(f'p{i}') for i in range(7)])
        return values+([self.choice(f'w{i}') for i in range(7)],) if well else values

class CDAITab(ScoreTab):
    def __init__(self,a):super().__init__(a,'CDAI','Complete the seven-day diary and all eight criteria.',
        'Bands: <150 remission; 150 to <220 mild; 220-450 moderate-severe; >450 severe. '
        'Hematocrit and weight terms retain their signs, matching the original HTML. No weight-term floor is applied; some trial protocols cap it at -10. Standard weight must follow the chosen clinical protocol.')
    def build(self):
        self.diary(True);self.add_section('Complications: one count per category')
        for i,s in enumerate(['Joint pain / arthritis','Iritis / uveitis','Erythema nodosum / pyoderma / aphthous ulcers','Anal fissure / fistula / abscess','Other fistulas','Fever >37.8 C during previous week']):self.entry(f'c{i}',s,YES)
        self.add_section('Other criteria')
        self.entry('drug','Diphenoxylate / opiates for diarrhea',YES)
        self.entry('mass','Abdominal mass',[('None',0),('Questionable',2),('Definite',5)])
        self.entry('ref','Sex/reference in original formula',[('Male: 47%',47),('Female: 42%',42)])
        self.entry('hct','Measured hematocrit (%) - enter 40, not 0.40')
        self.entry('weight','Current weight (kg)');self.entry('standard','Clinician-selected standard weight (kg)')
    def calculate(self):
        s,p,w=self.diary_values(True)
        total,band,pts=cdai(s,p,w,[self.choice(f'c{i}') for i in range(6)],self.choice('drug'),self.choice('mass'),self.choice('ref'),self.num('hct',1,75),self.num('weight',0.1),self.num('standard',0.1))
        names=['Stools x2','Pain x5','Well-being x7','Complications x20','Antidiarrheal x30','Mass x10','Hematocrit difference x6','Weight deviation %']
        return 'CDAI '+fmt(total)+' | '+band,table([['Component','Points']]+[[n,fmt(v)] for n,v in zip(names,pts)])

class HBITab(ScoreTab):
    def __init__(self,a):super().__init__(a,'HBI','Use the previous day for symptoms; examination findings require clinical assessment.',
        'Bands: 0-4 remission; 5-7 mild; 8-16 moderate; >16 severe. Add five component scores without multipliers. Clinical remission does not establish mucosal healing.')
    def build(self):
        self.add_section('Symptoms and examination')
        self.entry('well','General well-being yesterday',WELL);self.entry('pain','Abdominal pain yesterday',PAIN)
        self.entry('stools','Number of liquid stools yesterday (whole number)')
        self.entry('mass','Abdominal mass',[(s,i) for i,s in enumerate(['None','Questionable','Definite','Definite and tender'])])
        self.add_section('Complications: 1 point per type present')
        for i,s in enumerate(['Arthralgia','Uveitis','Erythema nodosum','Aphthous ulcers','Pyoderma gangrenosum','Anal fissure','New fistula','Abscess']):self.entry(f'c{i}',s,YES)
    def calculate(self):
        parts=[self.choice('well'),self.choice('pain'),self.num('stools',integer=True),self.choice('mass')]
        c=[self.choice(f'c{i}') for i in range(8)];total,band=hbi(*parts,c)
        return f'HBI {total} | {band}',table([['Component','Points']]+list(zip(['Well-being','Pain','Stools','Mass','Complications'],parts+[sum(c)])))

SEGMENTS=['Terminal ileum','Right colon','Transverse colon','Left colon (descending + sigmoid)','Rectum']
COVER=[('Assessed',1),('Not assessed / not evaluable',0),('Resected / not present',-1)]
class SESTab(ScoreTab):
    def __init__(self,a):super().__init__(a,'SES-CD','Enter four endoscopic features for each of five segments. Missing segments are never counted as normal.',
        'Common bands for a complete examination: 0-2 remission; 3-6 mild; 7-15 moderate; >=16 severe. Cutoffs vary by protocol. A partial observed sum has no global severity category. Maximum conventional score 56; more than one impassable narrowing requires review of examination coverage.')
    def build(self):
        options=[['No ulcers','<0.5 cm','0.5-2 cm','>2 cm'],['None','<10%','10-30%','>30%'],['Unaffected','<50%','50-75%','>75%'],['None','Single, passable','Multiple, passable','Not passable']]
        for i,n in enumerate(SEGMENTS):
            self.add_section(n);self.entry(f'cov{i}',n+': coverage',COVER)
            for j,s in enumerate(['Largest ulcer','Ulcerated surface','Affected surface','Narrowing']):self.entry(f'{i}_{j}',n+': '+s,[(f'{v} - {t}',v) for v,t in enumerate(options[j])])
    def calculate(self):
        for i in range(5):
            for j in range(4):self.fields[f'{i}_{j}'].setEnabled(self.selected(f'cov{i}')==1)
        rows=[];counts=[];vals=[]
        for i,n in enumerate(SEGMENTS):
            c=self.choice(f'cov{i}')
            if c!=1:rows.append([n,'Not scored']);continue
            v=[self.choice(f'{i}_{j}') for j in range(4)]
            if (v[0]==0)!=(v[1]==0) or v[2]<v[1]:raise ValueError(n+': ulcer size, ulcerated area and affected area are inconsistent.')
            counts.append(v[3]);vals.append(sum(v));rows.append([n,sum(v)])
        if not vals:raise ValueError('At least one assessed segment is required.')
        if counts.count(3)>1:raise ValueError('More than one impassable narrowing: review segment coverage before scoring.')
        total=sum(vals);complete=len(vals)==5
        band=('Endoscopic remission' if total<=2 else 'Mild activity' if total<=6 else 'Moderate activity' if total<=15 else 'Severe activity') if complete else 'Partial assessment - no global severity category'
        return f'{"SES-CD" if complete else "Partial observed sum"} {total} | {band}',table([['Segment','Subtotal']]+rows)

RUT={'i0':'No lesions.', 'i1':'1-5 aphthous ulcers in the neoterminal ileum.',
'i2':'More than 5 aphthous ulcers with normal intervening mucosa, patchy larger lesions, or lesions confined to the anastomosis (<1 cm length).',
'i2a':'Lesions confined to the ileocolonic anastomosis.',
'i2b':'More than 5 aphthous ulcers or patchy larger ileal lesions with normal intervening mucosa, with or without anastomotic lesions.',
'i3':'Diffuse aphthous ileitis with diffusely inflamed intervening mucosa.',
'i4':'Diffuse ileal inflammation with large ulcers, nodules and/or narrowing.'}
class RutTab(ScoreTab):
    def __init__(self,a):super().__init__(a,'Rutgeerts','Postoperative endoscopic category after ileocolonic resection with ileocolonic anastomosis.',
        'Original i2 or higher commonly defines endoscopic recurrence. i2a is not automatically benign; the prognostic distinction between i2a and i2b remains uncertain. This is a lesion category, not an additive score.')
    def build(self):
        self.add_section('Setting and version')
        self.entry('scope','Ileocolonic resection with ileocolonic anastomosis?',YES)
        self.entry('adequate','Neoterminal ileum and anastomosis adequately examined?',YES)
        self.entry('surgery','Surgery date (optional)')
        w=self.entry('version','Score version',[('Original','original'),('Modified','modified')])
        self.entry('grade','Endoscopic category',[]); w.currentIndexChanged.connect(self.grade_options)
        self.add_section('Category definitions')
        l=QLabel('\n\n'.join(k+': '+v for k,v in RUT.items()));l.setWordWrap(True);self.current.addRow(l)
    def grade_options(self):
        w=self.fields['grade'];w.blockSignals(True);w.clear();w.addItem('Select...',None)
        keys=['i0','i1','i2a','i2b','i3','i4'] if self.selected('version')=='modified' else ['i0','i1','i2','i3','i4']
        for k in keys:w.addItem(k,k)
        w.blockSignals(False);self.update_result()
    def calculate(self):
        if self.choice('scope')!=1:raise ValueError('Outside the intended postoperative setting. No category assigned.')
        if self.choice('adequate')!=1:raise ValueError('Incomplete examination. No definitive category assigned.')
        version=self.choice('version');g=self.choice('grade');original='i2' if g in ('i2a','i2b') else g
        status='Absent or minimal lesions' if g in ('i0','i1') else 'Advanced endoscopic recurrence' if g in ('i3','i4') else 'Recurrence threshold met'
        return f'{version.title()} {g} | {status}',para(RUT[g])+para('Original category: '+original)

class PROTab(ScoreTab):
    def __init__(self,a):super().__init__(a,'PRO2','Crohn\'s PRO2: seven-day stool-frequency and abdominal-pain diary (not UC-PRO2).',
        'Weighted daily PRO2 = 2 x mean daily liquid/very soft stools + 5 x mean pain (0-3). '
        'Component remission definitions vary by study; the selected threshold is reported explicitly. Symptoms do not establish endoscopic remission. All seven days are required; no missing-day imputation.')
    def build(self):
        self.add_section('Interpretation convention')
        self.entry('rule','Component threshold',[('SF <=1.5 and AP <=1.0 (Khanna-derived)',1.5),('SF <=2.8 and AP <=1.0 (trial threshold only)',2.8)])
        self.diary()
    def calculate(self):
        sf,ap,weighted=pro2(*self.diary_values());cut=self.choice('rule')
        meets=sf<=cut and ap<=1
        details=table([['Measure','Value'],['Mean daily stools',fmt(sf)],['Mean daily pain',fmt(ap)],['Weighted daily PRO2',fmt(weighted)],['Equivalent 7-day weighted sum',fmt(weighted*7)],['Selected component thresholds',f'SF <={cut}; AP <=1.0'],['Thresholds met?','Yes' if meets else 'No']])
        if cut==2.8:details+=para('Threshold check only: some trials additionally require no worsening from baseline and specified baseline symptom eligibility. Baseline criteria are not assessed here; this is not a full trial-remission adjudication.')
        return 'PRO2 '+fmt(weighted)+' | '+('Component thresholds met' if meets else 'Component thresholds not met'),details

MRSEG=['Terminal ileum','Ascending colon','Transverse colon','Descending colon','Sigmoid colon','Rectum']
class MRTab(ScoreTab):
    def __init__(self,a,simple=False):
        self.simple=simple
        super().__init__(a,'sMaRIA' if simple else 'MaRIA','MRI activity: six-segment scheme matching the existing HTML calculator. Requires trained image interpretation.',
            ('sMaRIA = 1(wall >3 mm) + edema + fat stranding + 2 x ulcers. Segment cutoffs: >=1 active; >=2 severe-activity cutoff in original validation (other cohorts used >=3). A score >=2 does not itself prove a visible ulcer.' if simple else
             'MaRIA = 1.5 x wall thickness (mm) + 0.02 x RCE (%) + 5 x edema + 10 x ulcers. Segment cutoffs: >=7 active; >=11 severe-activity cutoff. RCE = [(WSI post - WSI pre)/WSI pre] x100 x (SD noise pre/SD noise post).')+
            ' Cutoffs apply to individual segments, never the global sum. Unassessed/resected segments are excluded and the sum is labeled partial. This score does not quantify fibrosis or all complications.')
    def build(self):
        for i,n in enumerate(MRSEG):
            self.add_section(n);self.entry(f'cov{i}',n+': coverage',COVER)
            self.entry(f'wall{i}',n+': wall thickness (mm)')
            if not self.simple:self.entry(f'rce{i}',n+': relative contrast enhancement (%)')
            self.entry(f'e{i}',n+': edema',YES)
            if self.simple:self.entry(f'f{i}',n+': fat stranding',YES)
            self.entry(f'u{i}',n+': ulcers',YES)
    def calculate(self):
        prefixes=['wall','e','u']+(['f'] if self.simple else ['rce'])
        for i in range(6):
            for k in prefixes:self.fields[k+str(i)].setEnabled(self.selected(f'cov{i}')==1)
        rows=[];scores=[]
        for i,n in enumerate(MRSEG):
            if self.choice(f'cov{i}')!=1:rows.append([n,'Excluded','Not scored']);continue
            wall=self.num(f'wall{i}',0.01);e=self.choice(f'e{i}');u=self.choice(f'u{i}')
            value=smaria(wall,e,self.choice(f'f{i}'),u) if self.simple else maria(wall,self.num(f'rce{i}',-float('inf')),e,u)
            active,severe=(1,2) if self.simple else (7,11)
            status='Severe-activity cutoff met' if value>=severe else 'Active cutoff met' if value>=active else 'Below active cutoff'
            scores.append(value);rows.append([n,fmt(value),status])
        if not scores:raise ValueError('At least one assessed segment is required.')
        return ('Six-segment global total' if len(scores)==6 else 'Partial sum')+' = '+fmt(sum(scores)),table([['Segment','Score','Interpretation']]+rows)+para(f'{len(scores)}/6 segments scored. No global severity category is assigned.')

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('Crohn\'s disease | Clinical calculators');self.resize(1200,850)
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central)
        h=QLabel('Crohn\'s disease calculators');h.setObjectName('heading');layout.addWidget(h)
        m=QHBoxLayout();layout.addLayout(m)
        self.patient=QLineEdit();self.patient.setPlaceholderText('Patient / study ID (optional)')
        self.clinician=QLineEdit();self.clinician.setPlaceholderText('Clinician / reader (optional)')
        self.date=QDateEdit(QDate.currentDate());self.date.setCalendarPopup(True);self.date.setDisplayFormat('yyyy-MM-dd')
        m.addWidget(self.patient);m.addWidget(self.clinician);m.addWidget(QLabel('Assessment date'));m.addWidget(self.date)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.scores=[CDAITab(self),HBITab(self),SESTab(self),RutTab(self),PROTab(self),MRTab(self),MRTab(self,True)]
        for s in self.scores:self.tabs.addTab(s,s.title)
        label=QLabel('Offline | Entries are not stored automatically. Export reports before closing. | '+NOTICE);label.setWordWrap(True);layout.addWidget(label)
    def closeEvent(self,event):
        if QMessageBox.question(self,'Close application','Close and discard entered values? Save any reports first.')==QMessageBox.StandardButton.Yes:event.accept()
        else:event.ignore()

STYLE='''QWidget{font-family:Segoe UI,Arial;font-size:9pt;color:#183342} QMainWindow{background:#f1f6f8}
QLabel#heading{font-size:19pt;font-weight:700;color:#0f6772;padding:5px}
QGroupBox{font-weight:600;border:1px solid #cad9df;border-radius:7px;margin-top:14px;padding-top:15px;background:white}
QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 5px}
QLineEdit,QComboBox,QDateEdit{padding:6px;border:1px solid #b5cbd1;border-radius:4px;background:white;min-height:22px}
QPushButton{padding:9px;background:#0f6772;color:white;border-radius:5px;font-weight:600} QPushButton:hover{background:#194f61}
QTabBar::tab{padding:10px 18px;background:#e2edf1} QTabBar::tab:selected{background:#0f6772;color:white}
QTextBrowser{background:white;border:1px solid #cad9df;padding:12px} QScrollArea{border:none}'''

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    w=Window();w.show();sys.exit(app.exec())
if __name__=='__main__':main()
