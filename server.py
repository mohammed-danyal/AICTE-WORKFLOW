"""Account-based local demonstration service with scoped workspace access."""
import argparse
import base64
import json
import mimetypes
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from access import initialise_auth, session_user, login, logout, scoped, merge_authorised

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()
DB = ROOT / 'data' / 'portal.sqlite3'

@contextmanager
def connection():
    con = sqlite3.connect(DB, timeout=15)
    con.execute('PRAGMA journal_mode=WAL')
    try:
        with con:
            yield con
    finally:
        con.close()

def initialise():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connection() as con:
        con.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, name TEXT NOT NULL, data BLOB NOT NULL, created TEXT NOT NULL)')
        initialise_auth(con, DB.parent / 'LOCAL-ACCOUNTS.md')
        if 'case_id' not in {r[1] for r in con.execute('PRAGMA table_info(evidence)')}:
            con.execute('ALTER TABLE evidence ADD COLUMN case_id TEXT')
        if not con.execute('SELECT id FROM workspace WHERE id=1').fetchone():
            seed = json.loads((ROOT / 'seed.json').read_text(encoding='utf-8-sig'))
            seed.pop('role', None)
            con.execute('INSERT INTO workspace VALUES (1,1,?)', (json.dumps(seed),))
        revision,payload=con.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
        current=json.loads(payload);dirty=False
        for case in current['cases']:
            if 'documents' not in case:
                case['documents']=[{'name':n,'file':f,'reference':r,'status':'Pending','note':''} for n,f,r in [('Constitution / registration document','registration-certificate.pdf','Annexure 1 / 2 · applicability to be confirmed'),('Land / building possession evidence','registered-lease.pdf','Applicable ownership / lease requirement'),('Approved building plan','building-plan.pdf','Applicable building and infrastructure requirement')]]
                dirty=True
            for attachment in case.get('attachments',[]):con.execute('UPDATE evidence SET case_id=? WHERE id=? AND case_id IS NULL',(case['id'],attachment['id']))
        for obligation in current['obligations']:
            for attachment in obligation.get('attachments',[]):con.execute('UPDATE evidence SET case_id=? WHERE id=? AND case_id IS NULL',(obligation['caseId'],attachment['id']))
        if dirty:con.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1',(revision+1,json.dumps(current)))

def validate(data):
    if not isinstance(data, dict):
        raise ValueError('A workspace object is required.')
    for key in ['cases', 'obligations', 'audit', 'complaints']:
        if not isinstance(data.get(key), list) or len(data[key]) > 10000:
            raise ValueError('Invalid '+key+' collection.')
    if not isinstance(data.get('rule'), dict) or not isinstance(data.get('alertState'), dict):
        raise ValueError('Workflow configuration is missing.')
    datetime.strptime(data['date'], '%Y-%m-%d')
    def plain_text(value):
        if isinstance(value, str) and ('<' in value or '>' in value):
            raise ValueError('Use plain text without HTML or angle brackets.')
        if isinstance(value, dict):
            for item in value.values(): plain_text(item)
        elif isinstance(value, list):
            for item in value: plain_text(item)
    plain_text(data)
    ids = set()
    for case in data['cases']:
        if not all(isinstance(case.get(k), str) and case[k].strip() for k in ['id', 'name', 'stage', 'owner', 'due']):
            raise ValueError('Application identity, stage, owner and deadline are required.')
        if case['id'] in ids:
            raise ValueError('Application IDs must be unique.')
        ids.add(case['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', case['id']):
            raise ValueError('Invalid application ID.')
        for field in ['due', 'scheduled', 'submitted']:
            if case.get(field): datetime.strptime(case[field], '%Y-%m-%d')
        if not isinstance(case.get('route'), list) or case['stage'] not in case['route'] + ['Draft', 'Decision issued', 'Withdrawn']:
            raise ValueError('Application stage must belong to its workflow.')
    for obligation in data['obligations']:
        if obligation.get('caseId') not in ids:
            raise ValueError('An obligation references an unknown application.')
    data.pop('role', None)

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, content, mime='application/json', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def reply(self, status, data, extra=None):
        self.send_bytes(status, json.dumps(data).encode(), extra=extra)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {'error': 'This service accepts local requests only.'})
        route = urlparse(self.path).path
        if route.startswith('/api/'):
            with connection() as con:user=session_user(con,self.headers)
            if not user:return self.reply(401, {'error':'Sign in to access your workspace.'})
        if route == '/api/me':return self.reply(200, {'user':user})
        if route in ['/api/state', '/api/version']:
            with connection() as con:
                revision, payload = con.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
            return self.reply(200, {'revision': revision, 'username':user['username'], **({'state': scoped(json.loads(payload),user),'user':user} if route.endswith('state') else {})})
        if route.startswith('/api/evidence/'):
            with connection() as con:
                row = con.execute('SELECT name,data,case_id FROM evidence WHERE id=?', (route.rsplit('/', 1)[1],)).fetchone()
                payload=con.execute('SELECT payload FROM workspace WHERE id=1').fetchone()[0]
                allowed_cases={c['id'] for c in scoped(json.loads(payload),user)['cases']}
            if not row or row[2] not in allowed_cases:
                return self.reply(404, {'error': 'Evidence not found.'})
            from urllib.parse import quote
            return self.send_bytes(200, row[1], 'application/octet-stream', {'Content-Disposition': "attachment; filename*=UTF-8''"+quote(row[0])})
        if route == '/favicon.ico':
            return self.send_bytes(204, b'', 'image/x-icon')
        allowed = {'/': 'index.html', '/index.html': 'index.html', **{'/'+n: n for n in ['app.js', 'committee.js', 'portal.js', 'portal.css', 'live.js', 'live.css','auth.js','auth.css']}}
        name = allowed.get(route)
        if not name:
            return self.reply(404, {'error': 'Not found.'})
        file = ROOT / 'public' / name
        self.send_bytes(200, file.read_bytes(), (mimetypes.guess_type(name)[0] or 'text/plain')+'; charset=utf-8')

    def do_POST(self):
        origin = self.headers.get('Origin')
        if not self.valid_host() or (origin and origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}) or self.headers.get('X-Portal-Client') != 'aicte-local':
            return self.reply(403, {'error': 'Use the local portal to make changes.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'JSON content required.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8_000_000:
                return self.reply(413, {'error': 'Request exceeds the upload limit.'})
            body = json.loads(self.rfile.read(length))
            route = urlparse(self.path).path
            if route == '/api/login':
                with LOCK,connection() as con:user,token,error=login(con,body.get('username'),body.get('password'))
                if error:return self.reply(401,{'error':error})
                return self.reply(200,{'user':user},{'Set-Cookie':f'aicte_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800'})
            with connection() as con:user=session_user(con,self.headers)
            if not user:return self.reply(401,{'error':'Your session has expired. Sign in again.'})
            if route == '/api/logout':
                with connection() as con:logout(con,self.headers)
                return self.reply(200,{'ok':True},{'Set-Cookie':'aicte_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
            if route == '/api/state':
                with LOCK, connection() as con:
                    revision, previous = con.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
                    if body.get('revision') != revision:
                        return self.reply(409, {'error': 'Another session changed these records. Reload the latest version before retrying.', 'revision': revision})
                    before = json.loads(previous)
                    updated=merge_authorised(before,body['state'],user,con)
                    validate(updated)
                    con.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1', (revision+1, json.dumps(updated)))
                result=scoped(updated,user)
                return self.reply(200, {'revision': revision+1, 'audit': result['audit'], 'state':result})
            if route == '/api/evidence':
                with connection() as con:
                    payload=con.execute('SELECT payload FROM workspace WHERE id=1').fetchone()[0]
                    permitted={c['id'] for c in scoped(json.loads(payload),user)['cases']}
                if user['role']!='Institution' or body.get('caseId') not in permitted:
                    return self.reply(403,{'error':'Evidence uploads must belong to your institution.'})
                name = Path(str(body.get('name', '')).replace('\\', '/')).name
                if Path(name).suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg', '.docx'}:
                    return self.reply(400, {'error': 'Use PDF, PNG, JPG or DOCX evidence.'})
                content = base64.b64decode(body['content'], validate=True)
                if not content or len(content) > 5*1024*1024:
                    return self.reply(413, {'error': 'Evidence must be between 1 byte and 5 MB.'})
                evidence_id = uuid.uuid4().hex
                with connection() as con:
                    con.execute('INSERT INTO evidence (id,name,data,created,case_id) VALUES (?,?,?,?,?)', (evidence_id, name, content, datetime.now(timezone.utc).isoformat(),body['caseId']))
                return self.reply(201, {'id': evidence_id, 'name': name, 'size': len(content)})
            self.reply(404, {'error': 'Unknown action.'})
        except PermissionError as error:
            self.reply(403, {'error':str(error)})
        except (ValueError, KeyError, TypeError) as error:
            self.reply(400, {'error': str(error) or 'Invalid request.'})
        except Exception:
            self.reply(500, {'error': 'The change was not saved. Please retry.'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4190)
    parser.add_argument('--db', type=Path, default=DB)
    args = parser.parse_args()
    DB = args.db.resolve()
    initialise()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'AICTE Flow is running at http://127.0.0.1:{args.port}', flush=True)
    print(f'Data is saved in {DB}', flush=True)
    server.serve_forever()
