import os, json, sqlite3, secrets, time, hmac, re
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

BASE=Path(__file__).parent
DB=Path(os.getenv('DATABASE_PATH',str(BASE/'yhq.sqlite3')))
DB.parent.mkdir(parents=True,exist_ok=True)
ADMIN=os.getenv('ADMIN_LOGIN','admin')
PASSWORD=os.getenv('ADMIN_PASSWORD')
SECURE=os.getenv('COOKIE_SECURE','true').lower()!='false'
ph=PasswordHasher()
app=FastAPI(title='YHQ ACADEMY V24 — yagona platforma',docs_url=None,redoc_url=None)
@app.middleware('http')
async def security_headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    return response
def connect():
    c=sqlite3.connect(DB,timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=15000')
    return c
def init():
    with connect() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS users(login TEXT PRIMARY KEY, passhash TEXT NOT NULL, role TEXT NOT NULL, student_id TEXT UNIQUE, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(tokenhash TEXT PRIMARY KEY,login TEXT NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,ts INTEGER,actor TEXT,action TEXT,details TEXT);
CREATE TABLE IF NOT EXISTS lesson_files(id INTEGER PRIMARY KEY AUTOINCREMENT,day TEXT,name TEXT,mime TEXT,body BLOB);
CREATE TABLE IF NOT EXISTS daily_backup(id INTEGER PRIMARY KEY CHECK(id=1),day TEXT NOT NULL,body TEXT NOT NULL);
""")
        if not c.execute('SELECT 1 FROM state WHERE id=1').fetchone():
            c.execute('INSERT INTO state(id,value) VALUES(1,?)',(json.dumps({'groups':['YHQ-01'],'students':[],'marks':{},'lessons':{}}),))
        if PASSWORD and not c.execute("SELECT 1 FROM users WHERE role='teacher'").fetchone():
            c.execute('INSERT INTO users(login,passhash,role) VALUES(?,?,?)',(ADMIN,ph.hash(PASSWORD),'teacher'))
init()
class Login(BaseModel):
    login:str
    password:str
class Account(BaseModel):
    id:str
    login:str
    password:str
class Toggle(BaseModel):
    id:str
def log(c,actor,action,details=''):
    c.execute('INSERT INTO audit(ts,actor,action,details) VALUES(?,?,?,?)',(int(time.time()),actor,action,details[:300]))
def session(request:Request,role=None,write=False):
    token=request.cookies.get('yhq_session','')
    if not token:raise HTTPException(401,'Kirish talab qilinadi')
    import hashlib
    with connect() as c:
        row=c.execute('SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.login=s.login WHERE s.tokenhash=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
    if not row:raise HTTPException(401,'Sessiya tugagan')
    if role and row['role']!=role:raise HTTPException(403,'Ruxsat yo‘q')
    if write and not hmac.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']):
        raise HTTPException(403,'CSRF tekshiruvi o‘tmadi')
    return dict(row)
@app.get('/')
def home(request:Request):
    try:
        user=session(request)
        return RedirectResponse('/teacher' if user['role']=='teacher' else '/student',status_code=302)
    except HTTPException:return RedirectResponse('/login',status_code=302)
@app.get('/login')
def loginpage():return FileResponse(BASE/'static/login.html')
@app.post('/api/login')
def login(body:Login,response:Response):
    if len(body.login)>80 or len(body.password)>256:raise HTTPException(400,'Noto‘g‘ri ma’lumot')
    with connect() as c:
        u=c.execute('SELECT * FROM users WHERE login=? AND active=1',(body.login,)).fetchone()
        try:valid=bool(u) and ph.verify(u['passhash'],body.password)
        except (VerifyMismatchError,VerificationError):valid=False
        if not valid:raise HTTPException(401,'Login yoki parol xato')
        token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(24)
        import hashlib
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['login'],csrf,int(time.time())+7*86400))
    response.set_cookie('yhq_session',token,httponly=True,secure=SECURE,samesite='lax',max_age=7*86400)
    response.set_cookie('yhq_csrf',csrf,httponly=False,secure=SECURE,samesite='lax',max_age=7*86400)
    return {'role':u['role']}
@app.post('/api/logout')
def logout(request:Request,response:Response):
    user=session(request,write=True)
    import hashlib
    with connect() as c:c.execute('DELETE FROM sessions WHERE tokenhash=?',(hashlib.sha256(request.cookies['yhq_session'].encode()).hexdigest(),))
    response.delete_cookie('yhq_session');response.delete_cookie('yhq_csrf')
    return {'ok':True}
@app.get('/teacher')
def teacher(request:Request):
    session(request,'teacher')
    return FileResponse(BASE/'static/teacher.html')
@app.get('/student')
def student(request:Request):
    session(request,'student')
    return FileResponse(BASE/'static/student.html')
@app.get('/teacher-app.js')
def teacherjs(request:Request):
    session(request,'teacher')
    return FileResponse(BASE/'static/teacher-app.js',media_type='application/javascript')
@app.get('/api/teacher/state')
def get_state(request:Request):
    session(request,'teacher')
    with connect() as c:return json.loads(c.execute('SELECT value FROM state WHERE id=1').fetchone()['value'])
@app.put('/api/teacher/state')
async def put_state(request:Request):
    u=session(request,'teacher',write=True)
    raw=await request.body()
    if len(raw)>3_000_000:raise HTTPException(413,'Jurnal hajmi juda katta')
    try:data=json.loads(raw)
    except ValueError:raise HTTPException(400,'JSON xato')
    if not isinstance(data,dict) or not isinstance(data.get('students'),list) or not isinstance(data.get('marks'),dict) or not isinstance(data.get('groups'),list):
        raise HTTPException(400,'Jurnal tuzilmasi xato')
    if len(data['students'])>5000:raise HTTPException(413,'Juda ko‘p o‘quvchi')
    with connect() as c:
        c.execute('UPDATE state SET value=?,revision=revision+1 WHERE id=1',(json.dumps(data,ensure_ascii=False),))
        log(c,u['login'],'save_state',str(len(data['students'])))
        from datetime import datetime
        from zoneinfo import ZoneInfo
        day=datetime.now(ZoneInfo('Asia/Tashkent')).strftime('%Y-%m-%d')
        if not c.execute('SELECT 1 FROM daily_backup WHERE id=1 AND day=?',(day,)).fetchone():
            c.execute('INSERT INTO daily_backup(id,day,body) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET day=excluded.day,body=excluded.body',(day,json.dumps(data,ensure_ascii=False)))
    return {'ok':True}
@app.get('/api/teacher/accounts')
def accounts(request:Request):
    session(request,'teacher')
    with connect() as c:
        state=json.loads(c.execute('SELECT value FROM state WHERE id=1').fetchone()['value'])
        users={str(x['student_id']):dict(x) for x in c.execute("SELECT login,student_id,active FROM users WHERE role='student'")}
    return [{'id':str(s['id']),'name':s.get('name',''),'login':users.get(str(s['id']),{}).get('login'),'active':bool(users.get(str(s['id']),{}).get('active'))} for s in state['students']]
@app.post('/api/teacher/account')
def account(body:Account,request:Request):
    u=session(request,'teacher',write=True)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',body.login) or len(body.password)<8 or len(body.password)>128:
        raise HTTPException(400,'Login 3–40 belgi, parol kamida 8 belgi bo‘lsin')
    with connect() as c:
        state=json.loads(c.execute('SELECT value FROM state WHERE id=1').fetchone()['value'])
        if not any(str(s['id'])==body.id for s in state['students']):raise HTTPException(404,'O‘quvchi topilmadi')
        other=c.execute('SELECT student_id,role FROM users WHERE login=?',(body.login,)).fetchone()
        if other and (other['role']!='student' or other['student_id']!=body.id):raise HTTPException(409,'Bu login band')
        existing=c.execute("SELECT login FROM users WHERE student_id=? AND role='student'",(body.id,)).fetchone()
        if existing:
            c.execute('UPDATE users SET login=?,passhash=?,active=1 WHERE student_id=?',(body.login,ph.hash(body.password),body.id))
            c.execute('DELETE FROM sessions WHERE login=?',(existing['login'],))
        else:c.execute('INSERT INTO users(login,passhash,role,student_id) VALUES(?,?,?,?)',(body.login,ph.hash(body.password),'student',body.id))
        log(c,u['login'],'account_set',body.id)
    return {'ok':True,'login':body.login,'student_id':body.id}
@app.post('/api/teacher/account/toggle')
def toggle(body:Toggle,request:Request):
    u=session(request,'teacher',write=True)
    with connect() as c:
        row=c.execute("SELECT login,active FROM users WHERE student_id=? AND role='student'",(body.id,)).fetchone()
        if not row:raise HTTPException(404,'Login yaratilmagan')
        c.execute('UPDATE users SET active=? WHERE student_id=?',(0 if row['active'] else 1,body.id))
        c.execute('DELETE FROM sessions WHERE login=?',(row['login'],))
        log(c,u['login'],'toggle_student',body.id)
    return {'ok':True}

class StudentChange(BaseModel):
    current_password:str
    new_id:str
    new_login:str
    new_password:str|None=None

@app.get('/api/student/account')
def student_account(request:Request):
    u=session(request,'student')
    return {'id':u['student_id'],'login':u['login']}

@app.post('/api/student/account/change')
def student_change(body:StudentChange,request:Request,response:Response):
    u=session(request,'student',write=True)
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,32}',body.new_id):
        raise HTTPException(400,'ID 4–32 ta lotin harfi, raqam, _ yoki - bo‘lsin')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',body.new_login):
        raise HTTPException(400,'Login 3–40 ta lotin harfi, raqam, nuqta, _ yoki - bo‘lsin')
    if body.new_password is not None and (len(body.new_password)<8 or len(body.new_password)>128):
        raise HTTPException(400,'Yangi parol 8–128 belgi bo‘lsin')
    try:verified=ph.verify(u['passhash'],body.current_password)
    except (VerifyMismatchError,VerificationError):verified=False
    if not verified:raise HTTPException(403,'Joriy parol xato')
    oldid=str(u['student_id'])
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        clash=c.execute('SELECT login FROM users WHERE login=? AND login<>?',(body.new_login,u['login'])).fetchone()
        if clash:raise HTTPException(409,'Login band')
        state=json.loads(c.execute('SELECT value FROM state WHERE id=1').fetchone()['value'])
        if not any(str(x['id'])==oldid for x in state['students']):raise HTTPException(404,'O‘quvchi topilmadi')
        if body.new_id!=oldid:
            if any(str(x['id'])==body.new_id for x in state['students']):raise HTTPException(409,'ID band')
            for x in state['students']:
                if str(x['id'])==oldid:x['id']=body.new_id
            for k in ('marks','markTimes'):
                d=state.get(k,{})
                if isinstance(d,dict) and oldid in d:d[body.new_id]=d.pop(oldid)
            c.execute('UPDATE state SET value=?,revision=revision+1 WHERE id=1',(json.dumps(state,ensure_ascii=False),))
        hashvalue=ph.hash(body.new_password) if body.new_password else u['passhash']
        c.execute('UPDATE users SET login=?,student_id=?,passhash=? WHERE login=?',(body.new_login,body.new_id,hashvalue,u['login']))
        c.execute('DELETE FROM sessions WHERE login=?',(u['login'],))
        log(c,u['login'],'student_account_changed',f'{oldid} -> {body.new_id}; login updated')
    response.delete_cookie('yhq_session')
    response.delete_cookie('yhq_csrf')
    return {'ok':True,'relogin':True}

@app.get('/api/teacher/accounts/revision')
def accounts_revision(request:Request):
    session(request,'teacher')
    with connect() as c:
        row=c.execute('SELECT MAX(id) AS n FROM audit').fetchone()
        rev=c.execute('SELECT revision FROM state WHERE id=1').fetchone()
    return {'audit':row['n'] or 0,'state':rev['revision']}

@app.get('/api/student/me')
def my_data(request:Request):
    u=session(request,'student')
    with connect() as c:state=json.loads(c.execute('SELECT value FROM state WHERE id=1').fetchone()['value'])
    s=next((x for x in state['students'] if str(x['id'])==str(u['student_id'])),None)
    if not s:raise HTTPException(404,'O‘quvchi ro‘yxatda yo‘q')
    group=s.get('group')
    # Only own marks and identity; group ranking aggregate for peers without their detailed marks
    own={str(s['id']):state.get('marks',{}).get(str(s['id']),{})}
    peers=[{'id':x['id'],'name':x.get('name',''),'group':x.get('group','')} for x in state['students'] if x.get('group')==group]
    # ranking scores, no raw marks of others
    peer_scores={}
    for x in peers:
        vals=[(2.5 if v=='Y' else float(v)) for day in state.get('marks',{}).get(str(x['id']),{}).values() if isinstance(day,list) for v in day if v in ('Y',1,2,3,4,5)]
        peer_scores[str(x['id'])]=round(sum(vals)/len(vals),2) if vals else None
    return {'student':s,'data':{'students':[s],'groups':[group],'marks':own,'lessons':state.get('lessons',{}),'markTimes':{str(s['id']):state.get('markTimes',{}).get(str(s['id']),{})}},'ranking':[{'name':x['name'],'score':peer_scores[str(x['id'])],'me':str(x['id'])==str(s['id'])} for x in peers]}
@app.get('/health')
def health():return {'ok':True}

# Server-side lesson materials: available to authenticated students, no public URL.
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import io
@app.post('/api/teacher/lesson-file/{day}')
async def upload_lesson(day:str,request:Request,file:UploadFile=File(...)):
    u=session(request,'teacher',write=True)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise HTTPException(400,'Sana xato')
    content=await file.read(15*1024*1024+1)
    if len(content)>15*1024*1024:raise HTTPException(413,'15 MB limit')
    name=Path(file.filename or 'file').name[:160]
    with connect() as c:
        c.execute('INSERT INTO lesson_files(day,name,mime,body) VALUES(?,?,?,?)',(day,name,file.content_type or 'application/octet-stream',content))
        log(c,u['login'],'lesson_file_upload',day)
    return {'ok':True}
@app.get('/api/lesson-files/{day}')
def lesson_files(day:str,request:Request):
    session(request)
    with connect() as c:return [{'id':x['id'],'name':x['name'],'size':x['size']} for x in c.execute('SELECT id,name,length(body) size FROM lesson_files WHERE day=?',(day,))]
@app.get('/api/lesson-file/{file_id}')
def lesson_download(file_id:int,request:Request):
    session(request)
    with connect() as c:r=c.execute('SELECT name,mime,body FROM lesson_files WHERE id=?',(file_id,)).fetchone()
    if not r:raise HTTPException(404,'Fayl topilmadi')
    from urllib.parse import quote
    return StreamingResponse(io.BytesIO(r['body']),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(r['name'])})
@app.delete('/api/teacher/lesson-file/{file_id}')
def lesson_delete(file_id:int,request:Request):
    u=session(request,'teacher',write=True)
    with connect() as c:
        c.execute('DELETE FROM lesson_files WHERE id=?',(file_id,))
        log(c,u['login'],'lesson_file_delete',str(file_id))
    return {'ok':True}
@app.get('/api/teacher/backup')
def backup_download(request:Request):
    session(request,'teacher')
    with connect() as c:state=c.execute('SELECT value FROM state WHERE id=1').fetchone()['value']
    return Response(state,media_type='application/json',headers={'Content-Disposition':'attachment; filename="YHQ_V24_zahira.json"'})

app.mount('/',StaticFiles(directory=BASE/'static'),name='static')
