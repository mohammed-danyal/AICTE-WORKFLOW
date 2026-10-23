"""Authentication and record-level policies for the local prototype."""
import copy
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie

PAGES = {
    'Institution': ['Overview','Applications','Compliance','Document validity','Alerts','Audit trail'],
    'Supervisor': ['Overview','Applications','EVC scheduling','Committees','Complaints • SCSC','Compliance','Document validity','Alerts','Reports','Audit trail','Committee mandate'],
    'Scrutiny member': ['Overview','Scrutiny desk','Applications','Alerts','Audit trail','Committee mandate'],
    'EVC coordinator': ['Overview','EVC scheduling','Alerts','Audit trail','Committee mandate'],
    'EVC expert': ['Overview','EVC scheduling','Alerts','Audit trail','Committee mandate'],
    'SHC member': ['Overview','Committees','Alerts','Audit trail','Committee mandate'],
    'SAC member': ['Overview','Committees','Alerts','Audit trail','Committee mandate'],
    'SCSC member': ['Overview','Complaints • SCSC','Audit trail','Committee mandate'],
    'Compliance verifier': ['Overview','Compliance','Document validity','Alerts','Audit trail'],
    'Decision authority': ['Overview','Applications','Audit trail','Committee mandate'],
    'Rule author': ['Overview','Administration','Audit trail'],
    'Rule publisher': ['Overview','Administration','Audit trail'],
    'Technical administrator': ['Overview','Administration','Audit trail'],
    'Audit': ['Overview','Applications','Reports','Audit trail']
}
ACCOUNTS = [
 ('sunrise','Sunrise authorised signatory','Institution','Sunrise Institute of Technology'),
 ('coastal','Coastal authorised signatory','Institution','Coastal College of Engineering'),
 ('bureau','Bureau supervising officer','Supervisor',None),
 ('scrutiny','Scrutiny reviewer','Scrutiny member',None),
 ('evc-coordinator','EVC scheduling officer','EVC coordinator',None),
 ('evc-expert','EVC committee expert','EVC expert',None),
 ('hearing','Hearing committee member','SHC member',None),
 ('appeal','Appellate committee member','SAC member',None),
 ('complaints','Complaint committee member','SCSC member',None),
 ('compliance','Compliance verifier','Compliance verifier',None),
 ('decision','Delegated decision officer','Decision authority',None),
 ('rule-author','Workflow rule author','Rule author',None),
 ('rule-publisher','Workflow rule publisher','Rule publisher',None),
 ('admin','Technical administrator','Technical administrator',None),
 ('auditor','Read-only auditor','Audit',None)
]

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 250000).hex()

def initialise_auth(con, accounts_path):
    con.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, name TEXT, role TEXT, institution TEXT, salt TEXT, password_hash TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT, expires REAL)')
    con.execute('CREATE TABLE IF NOT EXISTS login_attempts (username TEXT, attempted REAL)')
    created=[]
    for username,name,role,institution in ACCOUNTS:
        if con.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
            continue
        password=username
        salt=secrets.token_hex(16)
        con.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',(username,name,role,institution,salt,password_hash(password,salt)))
        created.append((username,password,role,institution or 'Assigned staff workspace'))
    if created:
        with accounts_path.open('a',encoding='utf-8') as file:
            if accounts_path.stat().st_size == 0:
                file.write('# Local demonstration accounts\n\nDemo passwords match usernames. Quick login is available on the local login screen.\n\n| Username | Password | Workspace | Institution / scope |\n|---|---|---|---|\n')
            for row in created:
                file.write('| '+' | '.join(row)+' |\n')

def public_user(row):
    if not row: return None
    return dict(zip(['username','name','role','institution'],row[:4])) | {'pages': PAGES[row[2]]}

def session_user(con, headers):
    try:
        cookie=SimpleCookie();cookie.load(headers.get('Cookie',''))
        token=cookie['aicte_session'].value
    except Exception:
        return None
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=con.execute('SELECT u.username,u.name,u.role,u.institution FROM sessions s JOIN users u ON s.username=u.username WHERE s.token_hash=? AND s.expires>?',(digest,time.time())).fetchone()
    return public_user(row)

def login(con, username, password):
    if not isinstance(username,str) or not isinstance(password,str) or len(username)>100 or len(password)>300:
        raise ValueError('Enter a valid username and password.')
    username=username.strip().lower();now=time.time()
    con.execute('DELETE FROM login_attempts WHERE attempted<?',(now-900,))
    if con.execute('SELECT COUNT(*) FROM login_attempts WHERE username=? AND attempted>?',(username,now-60)).fetchone()[0]>=5:
        return None,None,'Too many attempts. Wait one minute before trying again.'
    row=con.execute('SELECT username,name,role,institution,salt,password_hash FROM users WHERE username=?',(username,)).fetchone()
    expected=row[5] if row else '0'*64
    actual=password_hash(password,row[4] if row else '0'*32)
    if not row or not hmac.compare_digest(actual,expected):
        con.execute('INSERT INTO login_attempts VALUES (?,?)',(username,now))
        return None,None,'Username or password is incorrect.'
    con.execute('DELETE FROM login_attempts WHERE username=?',(username,))
    con.execute('DELETE FROM sessions WHERE expires<?',(now,))
    token=secrets.token_urlsafe(32)
    con.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),username,now+8*3600))
    return public_user(row),token,None

def logout(con, headers):
    cookie=SimpleCookie();cookie.load(headers.get('Cookie',''))
    if 'aicte_session' in cookie:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(cookie['aicte_session'].value.encode()).hexdigest(),))

def visible_cases(state,user):
    role=user['role']
    if role=='Institution':return [c for c in state['cases'] if c['name']==user['institution']]
    stages={'Scrutiny member':['Scrutiny'],'EVC coordinator':['EVC'],'EVC expert':['EVC'],'SHC member':['SHC'],'SAC member':['SAC'],'Decision authority':['Decision','Decision issued']}
    if role in stages:return [c for c in state['cases'] if c['stage'] in stages[role] and (role!='EVC expert' or c.get('scheduled'))]
    if role in ['Supervisor','Compliance verifier','Audit']:return state['cases']
    return []

def scoped(state,user):
    result=copy.deepcopy(state)
    result['cases']=copy.deepcopy(visible_cases(state,user))
    ids={c['id'] for c in result['cases']}
    result['obligations']=[o for o in result['obligations'] if o['caseId'] in ids and user['role'] in ['Institution','Supervisor','Compliance verifier','Audit']]
    result['complaints']=result.get('complaints',[]) if user['role'] in ['Supervisor','SCSC member','Audit'] else []
    refs=ids|{o['id'] for o in result['obligations']}|{c['id'] for c in result['complaints']}
    if user['role'] in ['Rule author','Rule publisher','Technical administrator','Audit','Supervisor']:refs.add('System')
    result['audit']=[a for a in result['audit'] if a.get('ref') in refs]
    result['alertState']={k:v for k,v in result['alertState'].items() if any(k==i or k.startswith(i+'-') for i in refs)}
    if user['role'] not in ['Rule author','Rule publisher','Technical administrator']:
        result['rule']['draft']=None
    result.pop('role',None)
    return result

def changed(before,after):return {key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)}
def require(condition,message='This action is not permitted for your account.'):
    if not condition: raise PermissionError(message)

def check_case(old,new,user):
    role=user['role'];fields=changed(old,new);stage=old['stage']
    if not fields:return
    permitted=set()
    if role=='Institution':
        if stage=='Draft':permitted={'programme','category','stage','submitted','owner','version','stageDays'}
        elif old.get('finding'):permitted={'reply','owner','attachments'}
        if new['stage']!=stage:
            require(stage=='Draft' and new['stage']==old['route'][0] and new['owner']=='Scrutiny member')
        if 'reply' in fields:require(new.get('reply') and new['owner']=='Scrutiny member')
    elif role=='Supervisor':permitted={'owner'}
    elif role=='Scrutiny member' and stage=='Scrutiny':permitted={'documents','finding','reply','owner','due','stage'}
    elif role=='EVC coordinator' and stage=='EVC':permitted={'scheduled','owner'}
    elif role=='EVC expert' and stage=='EVC':
        permitted={'visited','report','stage','due','owner'}
        require(old.get('scheduled'),'A visit must be scheduled first.')
        if new.get('visited') and not old.get('visited'):require(old['scheduled']<=datetime.now().date().isoformat(),'The scheduled visit date has not arrived.')
        if new.get('report') and not old.get('report'):require(old.get('visited'),'Complete the visit first.')
        require(not old.get('visited') or new.get('visited'))
        require(not old.get('report') or new.get('report'))
    elif (role,stage) in [('SHC member','SHC'),('SAC member','SAC')]:permitted={'stage','due','owner','finding','reply'}
    elif role=='Decision authority' and stage=='Decision':
        permitted={'outcome','stage','history'}
        require(new['stage']=='Decision issued' and new.get('outcome') in ['Approval','Approval with conditions','Refused'])
    require(fields<=permitted,'This account cannot change: '+', '.join(sorted(fields-permitted)))
    if new['stage']!=stage and role not in ['Institution','Decision authority']:
        route=old['route'];index=route.index(stage)
        require(index+1<len(route) and new['stage']==route[index+1],'Invalid workflow transition.')
        if stage=='Scrutiny':require(new.get('documents') and all(d.get('status') in ['Verified','Not applicable'] and d.get('note') for d in new['documents']),'Complete document verification before routing.')
        if stage=='EVC':require(old.get('report') and old.get('visited'),'Complete the visit, report and sign-off sequence.')
        if old.get('finding'):require(old.get('reply'),'The institution must respond to the deficiency first.')

def merge_authorised(before,incoming,user,con):
    view=scoped(before,user);merged=copy.deepcopy(before);role=user['role']
    require(set(incoming)==set(view),'Unexpected workspace fields.')
    if incoming['date']!=view['date']:require(role=='Supervisor');merged['date']=incoming['date']
    if incoming['rule']!=view['rule']:
        require(role in ['Rule author','Rule publisher'])
        if role=='Rule author':require(changed(view['rule'],incoming['rule'])<={'draft'})
        if role=='Rule publisher':require(view['rule'].get('draft') and incoming['rule']==dict(view['rule']['draft'],draft=None))
        merged['rule']=incoming['rule']
    visible={c['id']:c for c in view['cases']};sent={c['id']:c for c in incoming['cases']}
    require(len(sent)==len(incoming['cases']) and visible.keys()<=sent.keys(),'Records cannot be deleted or duplicated.')
    all_ids={c['id'] for c in before['cases']}
    for key,c in sent.items():
        if key in visible:check_case(visible[key],c,user)
        else:
            require(role=='Institution' and key not in all_ids and c['name']==user['institution'],'Applications must belong to your institution.')
            require(c['stage']=='Draft' and c['owner']=='Institution' and c['route']==['Scrutiny','EVC','Decision'] and c['version']==before['rule']['version'])
            require(not c.get('outcome') and not c.get('history') and not c.get('finding') and not c.get('reply') and not c.get('visited') and not c.get('report'))
            require(all(d.get('status')=='Pending' and not d.get('note') for d in c.get('documents',[])))
        check_attachments(c.get('attachments',[]),key,con)
    merged['cases']=[sent.get(c['id'],c) for c in before['cases']]+[c for k,c in sent.items() if k not in all_ids]
    old_ob={o['id']:o for o in view['obligations']};new_ob={o['id']:o for o in incoming['obligations']}
    require(len(new_ob)==len(incoming['obligations']) and old_ob.keys()<=new_ob.keys())
    all_ob={o['id'] for o in before['obligations']}
    for key,o in new_ob.items():
        if key in old_ob:
            old=old_ob[key];fields=changed(old,o)
            allowed={'file','submitted','proposedExpiry','status','attachments'} if role=='Institution' and old['status']!='Accepted' else {'feedback','previousDue','due','status','fileHistory','file','submitted'} if role=='Compliance verifier' and old['status']=='Awaiting verification' else set()
            require(fields<=allowed,'You cannot verify or alter another institution’s obligation.')
            if role=='Institution' and fields:require(o['status']=='Awaiting verification' and o.get('file') and o.get('attachments'))
            if role=='Compliance verifier' and fields:
                require(o['status'] in ['Accepted','Pending','Clarification required'])
                if o['due']!=old['due']:require(o['due']==old.get('proposedExpiry') and o.get('previousDue')==old['due'])
        else:
            require(role=='Decision authority' and key not in all_ob)
            case=sent.get(o.get('caseId'));old_case=visible.get(o.get('caseId'))
            require(case and old_case and old_case['stage']=='Decision' and case['stage']=='Decision issued' and case['outcome']=='Approval with conditions')
            require(o['kind']=='Undertaking' and o['status']=='Pending')
        check_attachments(o.get('attachments',[]),o['caseId'],con)
    merged['obligations']=[new_ob.get(o['id'],o) for o in before['obligations']]+[o for k,o in new_ob.items() if k not in all_ob]
    old_com={c['id']:c for c in view['complaints']};new_com={c['id']:c for c in incoming['complaints']}
    require(old_com.keys()==new_com.keys())
    for key,c in new_com.items():
        fields=changed(old_com[key],c)
        require(not fields or role=='SCSC member' and fields<={'recommendation','notes','status'})
    merged['complaints']=[new_com.get(c['id'],c) for c in before.get('complaints',[])]
    refs=set(sent)|set(new_ob)|set(new_com)
    if role in ['Rule author','Rule publisher','Technical administrator','Supervisor']:refs.add('System')
    for key,value in incoming['alertState'].items():
        if view['alertState'].get(key)==value:continue
        require(any(key==i or key.startswith(i+'-') for i in refs))
        fields=changed(view['alertState'].get(key,{}),value)
        require(fields<=({'escalated','ack','delivered'} if role=='Supervisor' else {'ack','delivered'}))
        merged['alertState'][key]=value
    oldaudit=view['audit'];audit=incoming['audit']
    require(len(audit)>=len(oldaudit) and (not oldaudit or audit[-len(oldaudit):]==oldaudit),'Activity history cannot be edited.')
    events=audit[:len(audit)-len(oldaudit)]
    for event in events:
        require(event.get('ref') in refs,'Activity must reference an accessible record.')
        event['actor']=user['name']+' · '+role
        event['receivedAt']=datetime.now(timezone.utc).isoformat()
    merged['audit']=events+before['audit']
    return merged

def check_attachments(items,case_id,con):
    for item in items:
        row=con.execute('SELECT name,length(data),case_id FROM evidence WHERE id=?',(item.get('id'),)).fetchone()
        require(row and row[2]==case_id and row[0]==item.get('name') and row[1]==item.get('size'),'Evidence must belong to the same application.')
