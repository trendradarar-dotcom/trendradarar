import base64, hashlib, html, json, os, secrets, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path

AUTH_URL="https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL="https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL="https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
DIRECT_POST_INIT_URL="https://open.tiktokapis.com/v2/post/publish/video/init/"
UPLOAD_DRAFT_INIT_URL="https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL="https://open.tiktokapis.com/v2/post/publish/status/fetch/"
DEFAULT_SCOPES="user.info.basic,video.publish,video.upload"
STATE_TTL=600
SESSION_TTL=86400
MAX_UPLOAD_BYTES=100*1024*1024
DEMO_B64_PATH=Path(__file__).with_name("demo_video.b64")

_STATES={}
_SESSIONS={}
_LOCK=threading.Lock()

def cfg(name):
    return str(os.environ.get(name,"")).strip()

def configured():
    return all((cfg("TIKTOK_CLIENT_KEY"),cfg("TIKTOK_CLIENT_SECRET"),cfg("TIKTOK_REDIRECT_URI")))

def audit_approved():
    return cfg("TIKTOK_AUDIT_APPROVED").lower() in ("1","true","yes","on")

def fingerprint(v):
    return hashlib.sha256(v.encode()).hexdigest() if v else ""

def api_json_post(url, token, payload=None, timeout=25):
    body=json.dumps(payload or {}).encode("utf-8")
    req=urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization":f"Bearer {token}",
            "Content-Type":"application/json; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read(); status=r.status
    except urllib.error.HTTPError as e:
        raw=e.read(); status=e.code
    except Exception:
        return 0,{"error":{"code":"network_error","message":"TikTok API unreachable"}}
    try:
        parsed=json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        parsed={"error":{"code":"invalid_json","message":"Invalid TikTok response"}}
    return status,parsed

def query_creator(token):
    status,payload=api_json_post(CREATOR_INFO_URL,token,{})
    err=(payload.get("error") or {}) if isinstance(payload,dict) else {}
    data=(payload.get("data") or {}) if isinstance(payload,dict) else {}
    ok=(status==200 and err.get("code")=="ok")
    return ok,status,data,err

def load_demo_video():
    return base64.b64decode(DEMO_B64_PATH.read_text(encoding="utf-8").strip())

def mp4_duration_seconds(blob):
    i=blob.find(b"mvhd")
    if i<0 or i+8>=len(blob):
        return 0.0
    p=i+4
    version=blob[p]
    try:
        if version==0:
            if p+20>len(blob): return 0.0
            timescale=int.from_bytes(blob[p+12:p+16],"big")
            duration=int.from_bytes(blob[p+16:p+20],"big")
        elif version==1:
            if p+32>len(blob): return 0.0
            timescale=int.from_bytes(blob[p+20:p+24],"big")
            duration=int.from_bytes(blob[p+24:p+32],"big")
        else:
            return 0.0
        if timescale<=0 or duration<=0:
            return 0.0
        return duration/timescale
    except Exception:
        return 0.0

def clean_stores():
    now=int(time.time())
    with _LOCK:
        for k,v in list(_STATES.items()):
            if now-int(v.get("ts",0))>STATE_TTL:
                _STATES.pop(k,None)
        for sid,v in list(_SESSIONS.items()):
            if now-int(v.get("updated_at",0))>SESSION_TTL:
                _SESSIONS.pop(sid,None)

def page(title,body,extra_script=""):
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#0b0e12;--card:#151a21;--txt:#f5f7fa;--muted:#a9b0bb;--accent:#ff2d55;--line:#2a313b;--ok:#28c76f}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--txt);font-family:Arial,Tahoma,sans-serif;line-height:1.55}}
.wrap{{max-width:880px;margin:auto;padding:28px 18px 60px}} .brand{{display:flex;gap:14px;align-items:center;margin-bottom:24px}}
.logo{{width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,#25f4ee,#111,#fe2c55);display:grid;place-items:center;font-weight:800}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;margin:16px 0}}
h1,h2{{margin:0 0 12px}} p{{margin:8px 0;color:var(--muted)}} a{{color:#74d9ff}}
button,.btn{{display:inline-block;border:0;border-radius:12px;padding:13px 20px;background:var(--accent);color:white;font-weight:700;text-decoration:none;cursor:pointer}}
button[disabled]{{opacity:.5;cursor:not-allowed}} label{{display:block;margin:14px 0 6px;font-weight:700}}
input[type=text],select,input[type=file]{{width:100%;background:#0f1318;color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:12px}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .check{{display:flex;gap:10px;align-items:center;margin:10px 0;font-weight:400}}
small,.muted{{color:var(--muted)}} video{{width:100%;max-height:420px;background:#000;border-radius:12px;margin-top:12px}}
.status{{padding:12px;border-radius:10px;background:#0f1318;border:1px solid var(--line);white-space:pre-wrap;direction:ltr;text-align:left}}
.ok{{color:var(--ok)}} .danger{{color:#ff6b6b}} footer{{margin-top:30px;color:var(--muted);font-size:14px}}
@media(max-width:650px){{.row{{grid-template-columns:1fr}}}}
</style>
</head><body><div class="wrap">
<div class="brand"><div class="logo">TR</div><div><strong>رادار الترند — Trend Radar</strong><br><small>اكتشف ما يصعد الآن في بلدك والعالم</small></div></div>
{body}
<footer>
<a href="/privacy">سياسة خصوصية TikTok</a> ·
<a href="/terms">شروط استخدام TikTok</a>
<br>تكامل TikTok يستخدم Login Kit وContent Posting API لمشاركة المحتوى الأصلي بموافقة المستخدم.
</footer></div>{extra_script}</body></html>"""

class Handler(BaseHTTPRequestHandler):
    server_version="TrendRadarTikTokShare/2.0"

    def log_message(self,fmt,*args):
        path=urllib.parse.urlsplit(self.path).path
        print(f"{self.address_string()} - {self.command} {path} - {fmt % args}", flush=True)

    def end_headers(self):
        for k,v in {
            "Cache-Control":"no-store","Pragma":"no-cache",
            "X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY",
            "Referrer-Policy":"no-referrer",
            "Permissions-Policy":"camera=(),microphone=(),geolocation=()",
            "Content-Security-Policy":"default-src 'self'; img-src 'self' data: https:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        }.items(): self.send_header(k,v)
        super().end_headers()

    def send_bytes(self,status,body,ctype="text/html; charset=utf-8",headers=None):
        self.send_response(status)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        for k,v in (headers or {}).items():
            self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)

    def send_html(self,status,text,headers=None):
        self.send_bytes(status,text.encode("utf-8"),headers=headers)

    def js(self,status,payload,headers=None):
        body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        self.send_bytes(status,body,"application/json; charset=utf-8",headers)

    def cookie_sid(self):
        raw=self.headers.get("Cookie","")
        c=SimpleCookie()
        try: c.load(raw)
        except Exception: return ""
        morsel=c.get("trsid")
        return morsel.value if morsel else ""

    def get_session(self):
        sid=self.cookie_sid()
        if not sid: return "",None
        with _LOCK:
            sess=_SESSIONS.get(sid)
            if sess: sess["updated_at"]=int(time.time())
        return sid,sess

    def set_cookie_header(self,sid):
        return {"Set-Cookie":f"trsid={sid}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}"}

    def redirect(self,url,headers=None):
        self.send_response(302)
        self.send_header("Location",url)
        self.send_header("Content-Length","0")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()

    def do_GET(self):
        clean_stores()
        p=urllib.parse.urlsplit(self.path)
        q=urllib.parse.parse_qs(p.query,keep_blank_values=True)

        if p.path=="/":
            body="""<div class="card"><h1>شارك فيديوك الأصلي على TikTok</h1>
<p>اربط حساب TikTok، راجع الحساب المستهدف وخيارات الخصوصية، عاين الفيديو، ثم أرسل فقط بعد موافقتك الصريحة.</p>
<p>لا نضيف شعارًا أو علامة مائية إلى الفيديو، ولا نرسل أي ملف قبل ضغطك زر النشر.</p>
<a class="btn" href="/auth/tiktok/start">ربط حساب TikTok</a></div>
<div class="card"><h2>كيف يعمل؟</h2>
<p>1) تسجيل الدخول الآمن عبر TikTok. 2) جلب إعدادات حسابك الحالية. 3) اختيار فيديو أصلي من جهازك. 4) اختيار الخصوصية والتفاعلات المتاحة لحسابك. 5) مراجعة الإعدادات والموافقة الصريحة. 6) الإرسال إلى TikTok ومتابعة حالة النشر.</p>
<p>هذه خدمة موجهة لمنشئي المحتوى المخولين لربط حساباتهم ومشاركة محتواهم الأصلي بإرادتهم؛ لا يتم النشر تلقائيًا أو دون إجراء واضح من المستخدم.</p></div>"""
            return self.send_html(200,page("Trend Radar · Share to TikTok",body))

        if p.path=="/health":
            return self.js(200,{"ok":True,"configured":configured(),"ui":"creator_facing_v3","audit_approved":audit_approved(),"scopes":cfg("TIKTOK_SCOPES") or DEFAULT_SCOPES})

        if p.path=="/privacy":
            body="""<div class="card"><h1>سياسة خصوصية تكامل TikTok</h1>
<p>آخر تحديث: 22 سبتمبر 2026</p>
<h2>ما الذي نصل إليه؟</h2>
<p>عندما يربط المستخدم حساب TikTok، نستخدم فقط الصلاحيات التي وافق عليها لتحديد الحساب المخول وتنفيذ عملية نشر مباشر أو رفع كمسودة يطلبها المستخدم ومتابعة حالتها. لا نطلب كلمة مرور TikTok.</p>
<h2>كيف نستخدم البيانات؟</h2>
<p>نستخدم بيانات الحساب الأساسية ومعلومات Creator Info اللازمة لعرض الحساب المستهدف وخيارات الخصوصية والقيود الحالية. يمكن للمستخدم اختيار Direct Post بعد مراجعة الإعدادات والموافقة الصريحة، أو اختيار رفع الفيديو كمسودة إلى TikTok لاستكمال التحرير والنشر من داخل TikTok.</p>
<h2>رموز التفويض والأمان</h2>
<p>تتم معالجة access token وrefresh token على الخادم ولا نعرض قيمهما الصريحة للمتصفح. نحتفظ ببيانات التفويض فقط بقدر ما يلزم لتقديم الاتصال المصرح به وتشغيله.</p>
<h2>المشاركة والبيع</h2>
<p>لا نبيع بيانات مستخدمي TikTok ولا نستخدمها للإعلانات المخصصة أو التقييم الائتماني. لا ننقلها إلا بالقدر اللازم لتقديم الوظيفة التي طلبها المستخدم أو للامتثال لالتزام نظامي مشروع.</p>
<h2>التحكم والحذف</h2>
<p>يمكن للمستخدم إلغاء تفويض Trend Radar من TikTok. عند انتهاء أو إلغاء الاتصال نتوقف عن استخدام التفويض، ويمكن طلب حذف البيانات القابلة للحذف المرتبطة به عبر البريد أدناه.</p>
<h2>المحتوى</h2>
<p>الفيديو يختاره المستخدم من جهازه. لا نضيف علامة مائية أو رابطًا ترويجيًا إلى الفيديو قبل إرساله إلى TikTok.</p>
<h2>التواصل</h2>
<p><a href="mailto:trendradarar@gmail.com">trendradarar@gmail.com</a></p></div>"""
            return self.send_html(200,page("TikTok Privacy · Trend Radar",body))

        if p.path=="/terms":
            body="""<div class="card"><h1>شروط استخدام تكامل TikTok</h1>
<p>آخر تحديث: 22 سبتمبر 2026</p>
<h2>نطاق الخدمة</h2>
<p>يوفر Trend Radar واجهة لمنشئي المحتوى المخولين لربط حساب TikTok واختيار فيديو أصلي ومراجعة إعدادات النشر ثم إرساله بإجراء صريح من المستخدم.</p>
<h2>التفويض والتحكم</h2>
<p>يقر المستخدم بأنه مخول بربط الحساب المستهدف. يبقى المستخدم صاحب القرار في منح الصلاحيات أو إلغائها واختيار الفيديو والوصف والخصوصية وإعدادات التفاعل.</p>
<h2>المحتوى والحقوق</h2>
<p>يجب ألا يرسل المستخدم إلا محتوى يملك حق نشره، وأن يلتزم بحقوق الملكية الفكرية وسياسات TikTok والأنظمة المعمول بها.</p>
<h2>لا نشر صامت</h2>
<p>لا يبدأ Direct Post ولا رفع المسودة إلا بعد اختيار المستخدم للفيديو وتأكيد الموافقة الصريحة والضغط على الزر المقابل للعملية.</p>
<h2>الخصوصية</h2>
<p>توضح <a href="/privacy">سياسة خصوصية TikTok</a> كيفية استخدام بيانات التفويض والمعلومات التشغيلية المرتبطة بالتكامل.</p>
<h2>التواصل</h2>
<p><a href="mailto:trendradarar@gmail.com">trendradarar@gmail.com</a></p></div>"""
            return self.send_html(200,page("TikTok Terms · Trend Radar",body))

        if p.path=="/auth/tiktok/start":
            return self.start_auth(q)

        if p.path=="/auth/tiktok/callback":
            return self.callback(q)

        if p.path=="/share":
            return self.share_page()

        if p.path=="/api/status":
            return self.status_api(q)

        if p.path=="/private-test":
            return self.private_test_page(q)

        if p.path=="/auth/tiktok/status":
            sid,sess=self.get_session()
            return self.js(200,{
                "configured":configured(),
                "authorized":bool(sess and sess.get("access_token")),
                "scope":(sess or {}).get("scope",""),
                "publication_authority":False,
                "token_plaintext_exposed":False,
            })
        return self.js(404,{"error":"not_found"})

    def do_POST(self):
        p=urllib.parse.urlsplit(self.path)
        if p.path=="/api/post":
            return self.post_video(p)
        if p.path=="/api/private-test":
            return self.private_test_post()
        if p.path=="/api/upload-draft":
            return self.upload_draft(p)
        return self.js(404,{"error":"not_found"})

    def start_auth(self,q=None):
        q=q or {}
        if not configured():
            return self.send_html(503,page("Configuration required","<div class='card'><h1>الخدمة غير مهيأة</h1></div>"))
        sid=self.cookie_sid() or secrets.token_urlsafe(24)
        csrf=secrets.token_urlsafe(24)
        now=int(time.time())
        with _LOCK:
            sess=_SESSIONS.get(sid) or {}
            sess.update({"csrf":csrf,"updated_at":now})
            _SESSIONS[sid]=sess
            state=secrets.token_urlsafe(32)
            requested_next=q.get("next",["/share"])[0]
            next_path="/private-test" if requested_next=="/private-test" else "/share"
            _STATES[state]={"sid":sid,"ts":now,"next_path":next_path}
        params={
            "client_key":cfg("TIKTOK_CLIENT_KEY"),
            "response_type":"code",
            "scope":cfg("TIKTOK_SCOPES") or DEFAULT_SCOPES,
            "redirect_uri":cfg("TIKTOK_REDIRECT_URI"),
            "state":state,
            "disable_auto_auth":"1",
        }
        return self.redirect(AUTH_URL+"?"+urllib.parse.urlencode(params),self.set_cookie_header(sid))

    def callback(self,q):
        if q.get("error"):
            return self.send_html(400,page("Authorization failed","<div class='card'><h1>تعذر التفويض</h1><p>ألغى المستخدم العملية أو رفض TikTok الطلب.</p></div>"))
        state=q.get("state",[""])[0]; code=q.get("code",[""])[0]; now=int(time.time())
        with _LOCK:
            item=_STATES.pop(state,None) if state else None
        if not item or now-int(item.get("ts",0))>STATE_TTL:
            return self.send_html(400,page("Invalid state","<div class='card'><h1>جلسة التفويض غير صالحة</h1><a class='btn' href='/auth/tiktok/start'>ابدأ من جديد</a></div>"))
        sid=item["sid"]
        next_path=item.get("next_path","/share")
        if not code:
            return self.send_html(400,page("Missing code","<div class='card'><h1>لم يصل رمز التفويض</h1></div>"))
        data=urllib.parse.urlencode({
            "client_key":cfg("TIKTOK_CLIENT_KEY"),
            "client_secret":cfg("TIKTOK_CLIENT_SECRET"),
            "code":code,
            "grant_type":"authorization_code",
            "redirect_uri":cfg("TIKTOK_REDIRECT_URI"),
        }).encode()
        req=urllib.request.Request(TOKEN_URL,data=data,headers={"Content-Type":"application/x-www-form-urlencoded"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=20) as r:
                payload=json.loads(r.read().decode("utf-8"))
        except Exception:
            return self.send_html(502,page("Token exchange failed","<div class='card'><h1>تعذر إكمال تسجيل الدخول</h1></div>"))
        access=str(payload.get("access_token","")).strip()
        refresh=str(payload.get("refresh_token","")).strip()
        open_id=str(payload.get("open_id","")).strip()
        scope=str(payload.get("scope","")).strip()
        exp=int(payload.get("expires_in",0) or 0)
        if not access or not refresh or not open_id or exp<=0:
            return self.send_html(502,page("Incomplete token","<div class='card'><h1>استجابة TikTok غير مكتملة</h1></div>"))
        with _LOCK:
            sess=_SESSIONS.get(sid) or {"csrf":secrets.token_urlsafe(24)}
            sess.update({
                "access_token":access,"refresh_token":refresh,"open_id":open_id,
                "scope":scope,"expires_at":now+exp,"updated_at":now,
                "access_token_sha256":fingerprint(access),"refresh_token_sha256":fingerprint(refresh),
            })
            _SESSIONS[sid]=sess
        return self.redirect(next_path,self.set_cookie_header(sid))

    def share_page(self):
        sid,sess=self.get_session()
        if not sess or not sess.get("access_token"):
            return self.redirect("/auth/tiktok/start")
        ok,status,data,err=query_creator(sess["access_token"])
        if not ok:
            code=html.escape(str(err.get("code") or status))
            return self.send_html(502,page("Creator info failed",f"<div class='card'><h1>تعذر قراءة إعدادات TikTok</h1><p class='danger'>{code}</p></div>"))
        with _LOCK:
            sess["creator_info"]=data; sess["updated_at"]=int(time.time())
        nickname=html.escape(str(data.get("creator_nickname") or data.get("creator_username") or "TikTok creator"))
        username=html.escape(str(data.get("creator_username") or ""))
        avatar=html.escape(str(data.get("creator_avatar_url") or ""))
        privacy=list(data.get("privacy_level_options") or [])
        approved=audit_approved()
        account_private=("PUBLIC_TO_EVERYONE" not in privacy and "FOLLOWER_OF_CREATOR" in privacy)
        option_rows=[]
        for x in privacy:
            disabled=(not approved and x!="SELF_ONLY")
            suffix=" — متاح بعد اعتماد TikTok" if disabled else ""
            option_rows.append(f"<option value='{html.escape(str(x))}' {'disabled' if disabled else ''}>{html.escape(str(x))+suffix}</option>")
        privacy_options="<option value=''>اختر الخصوصية يدويًا</option>"+"".join(option_rows)
        if approved:
            audit_notice=""
        elif account_private:
            audit_notice="<p class='muted'>وضع ما قبل التدقيق: الاختبار مسموح فقط بخصوصية SELF_ONLY حتى اعتماد TikTok.</p>"
        else:
            audit_notice="<p class='danger'><strong>يلزم جعل حساب TikTok خاصًا (Private) قبل اختبار Direct Post في وضع ما قبل التدقيق.</strong> لن نرسل أي محاولة نشر حتى يصبح الحساب خاصًا.</p>"
        comment_disabled=bool(data.get("comment_disabled"))
        duet_disabled=bool(data.get("duet_disabled"))
        stitch_disabled=bool(data.get("stitch_disabled"))
        max_sec=int(data.get("max_video_post_duration_sec") or 0)
        avatar_html=f"<img src='{avatar}' alt='' style='width:64px;height:64px;border-radius:50%;object-fit:cover'>" if avatar else ""
        body=f"""<div class="card"><h1>النشر إلى TikTok</h1>
<div style="display:flex;gap:14px;align-items:center">{avatar_html}<div><strong>{nickname}</strong><br><small>@{username}</small></div></div>
<p>الحد الأقصى لهذا الحساب: <strong>{max_sec} ثانية</strong>.</p>{audit_notice}</div>
<div class="card">
<label>الفيديو الأصلي من جهازك</label><input id="videoFile" type="file" accept="video/mp4" required>
<video id="preview" controls hidden></video>
<label>العنوان / الوصف</label><input id="title" type="text" maxlength="2200" placeholder="اكتب وصفك بنفسك — لا يوجد نص مفروض">
<label>الخصوصية</label><select id="privacy" required>{privacy_options}</select>
<div class="row"><div>
<label class="check"><input id="comment" type="checkbox" {'disabled' if comment_disabled else ''}> السماح بالتعليقات</label>
<label class="check"><input id="duet" type="checkbox" {'disabled' if duet_disabled else ''}> السماح بـ Duet</label>
<label class="check"><input id="stitch" type="checkbox" {'disabled' if stitch_disabled else ''}> السماح بـ Stitch</label>
</div><div><p class="muted">لا يتم تفعيل أي تفاعل افتراضيًا. الخيارات المعطلة تعكس إعدادات حسابك الحالية في TikTok.</p></div></div>
<label class="check"><input id="commercial" type="checkbox"> هذا محتوى تجاري</label>
<div id="commercialNote" class="danger" hidden>النشر التجاري غير مدعوم في هذه النسخة؛ ألغِ هذا الخيار للمتابعة.</div>
<label class="check"><input id="consent" type="checkbox"> أؤكد أنني أملك حق مشاركة هذا المحتوى، وأوافق صراحة على إرساله إلى TikTok. وبالنشر أوافق على تأكيد استخدام الموسيقى في TikTok.</label>
<div class="row">
<div><button id="publish" disabled>نشر مباشر إلى TikTok</button></div>
<div><button id="draft" disabled>رفع كمسودة إلى TikTok</button></div>
</div>
<p class="muted">النشر المباشر يستخدم الإعدادات أعلاه. رفع المسودة يرسل الفيديو إلى TikTok Inbox لتكمل التحرير والنشر من داخل TikTok.</p>
<div id="status" class="status" hidden></div></div>"""
        script=f"""<script>
const maxSec={max_sec}; const csrf={json.dumps(sess.get("csrf",""))}; const preAuditBlocked={str((not approved and not account_private)).lower()};
const f=document.getElementById('videoFile'), p=document.getElementById('preview'), btn=document.getElementById('publish'), draftBtn=document.getElementById('draft');
const privacy=document.getElementById('privacy'), consent=document.getElementById('consent'), commercial=document.getElementById('commercial');
let duration=0;
function ready(){{
 document.getElementById('commercialNote').hidden=!commercial.checked;
 btn.disabled=preAuditBlocked || !(f.files.length&&privacy.value&&consent.checked&&!commercial.checked);
 draftBtn.disabled=!(f.files.length&&consent.checked&&!commercial.checked);
}}
[f,privacy,consent,commercial].forEach(x=>x.addEventListener('change',ready));
f.addEventListener('change',()=>{{duration=0; if(!f.files.length) return ready(); ready(); const u=URL.createObjectURL(f.files[0]); p.src=u;p.hidden=false;p.onloadedmetadata=()=>{{duration=p.duration;ready();}};p.onerror=()=>{{duration=0;ready();}};}});
draftBtn.addEventListener('click',async()=>{{
 draftBtn.disabled=true; const s=document.getElementById('status'); s.hidden=false;s.textContent='Uploading draft...';
 const file=f.files[0];
 try{{
  const r=await fetch('/api/upload-draft?consent=true&duration_sec='+encodeURIComponent(String(duration)),{{method:'POST',headers:{{'Content-Type':'video/mp4','X-CSRF-Token':csrf}},body:file}});
  const j=await r.json(); if(!r.ok){{s.textContent='Draft error: '+JSON.stringify(j);ready();return;}}
  s.textContent='Draft accepted. TikTok is processing it…\nPublish ID: '+j.publish_id+'\nبعد الإرسال افتح TikTok Inbox لإكمال التحرير والنشر.';
  poll(j.publish_id,s);
 }}catch(e){{s.textContent='Draft upload failed';ready();}}
}});
btn.addEventListener('click',async()=>{{
 btn.disabled=true; const s=document.getElementById('status'); s.hidden=false;s.textContent='Uploading...';
 const file=f.files[0];
 const q=new URLSearchParams({{
  title:document.getElementById('title').value,
  privacy:privacy.value,
  duration_sec:String(duration),
  allow_comment:String(document.getElementById('comment').checked),
  allow_duet:String(document.getElementById('duet').checked),
  allow_stitch:String(document.getElementById('stitch').checked),
  consent:'true'
 }});
 try{{
  const r=await fetch('/api/post?'+q.toString(),{{method:'POST',headers:{{'Content-Type':'video/mp4','X-CSRF-Token':csrf}},body:file}});
  const j=await r.json(); if(!r.ok){{s.textContent='Error: '+JSON.stringify(j);ready();return;}}
  s.textContent='Upload accepted. Processing…\nPublish ID: '+j.publish_id;
  poll(j.publish_id,s);
 }}catch(e){{s.textContent='Upload failed';ready();}}
}});
async function poll(id,s){{
 for(let i=0;i<30;i++){{
  await new Promise(r=>setTimeout(r,2500));
  const r=await fetch('/api/status?publish_id='+encodeURIComponent(id));
  const j=await r.json(); s.textContent='TikTok status:\n'+JSON.stringify(j,null,2);
  const st=((j.data||{{}}).status||'').toUpperCase();
  if(st==='FAILED'||st==='PUBLISH_COMPLETE'||st==='SEND_TO_USER_INBOX') return;
 }}
}}
</script>"""
        return self.send_html(200,page("Share to TikTok",body,script))

    def private_test_page(self,q):
        sid,sess=self.get_session()
        if not sess or not sess.get("access_token"):
            return self.redirect("/auth/tiktok/start?next=%2Fprivate-test")
        ok,status,creator,err=query_creator(sess["access_token"])
        if not ok:
            code=html.escape(str(err.get("code") or status))
            return self.send_html(502,page("Private test blocked",f"<div class='card'><h1>تعذر قراءة إعدادات TikTok</h1><p class='danger'>{code}</p></div>"))
        options=list(creator.get("privacy_level_options") or [])
        approved=audit_approved()
        account_private=("PUBLIC_TO_EVERYONE" not in options and "FOLLOWER_OF_CREATOR" in options)
        if not approved and not account_private:
            return self.send_html(400,page("Private account required","<div class='card'><h1>الحساب يجب أن يبقى Private للاختبار قبل التدقيق.</h1></div>"))
        result_html=""
        publish_id=q.get("publish_id",[""])[0]
        if publish_id:
            st,payload=api_json_post(STATUS_URL,sess["access_token"],{"publish_id":publish_id})
            safe=html.escape(json.dumps(payload,ensure_ascii=False,indent=2))
            result_html=f"<div class='card'><h2>حالة TikTok</h2><pre class='status'>{safe}</pre></div>"
        body=f"""<div class="card"><h1>اختبار TikTok الخاص من الخادم</h1>
<p>هذا الاختبار لا يرفع ملفًا من المتصفح. يستخدم فيديو الاختبار المحايد الموجود داخل الخدمة ويرسله بخصوصية <strong>SELF_ONLY</strong> فقط.</p>
<form method="post" action="/api/private-test">
<input type="hidden" name="csrf" value="{html.escape(sess.get('csrf',''))}">
<button type="submit">تشغيل الاختبار الخاص الآن</button>
</form></div>{result_html}"""
        return self.send_html(200,page("TikTok private server test",body))

    def private_test_post(self):
        sid,sess=self.get_session()
        if not sess or not sess.get("access_token"):
            return self.redirect("/auth/tiktok/start")
        try:
            length=int(self.headers.get("Content-Length","0"))
        except Exception:
            length=0
        raw=self.rfile.read(length) if length>0 else b""
        form=urllib.parse.parse_qs(raw.decode("utf-8",errors="ignore"),keep_blank_values=True)
        if form.get("csrf",[""])[0]!=sess.get("csrf",""):
            return self.js(403,{"error":"csrf_failed"})

        print("PRIVATE_TEST stage=load_demo", flush=True)
        try:
            video=load_demo_video()
        except Exception:
            return self.js(500,{"error":"demo_video_unavailable"})
        duration=mp4_duration_seconds(video)
        if duration<=0:
            return self.js(500,{"error":"demo_video_invalid"})

        print("PRIVATE_TEST stage=creator_info", flush=True)
        ok,status,creator,err=query_creator(sess["access_token"])
        if not ok:
            return self.js(502,{"error":"creator_info_failed","provider_code":err.get("code"),"http_status":status})
        options=list(creator.get("privacy_level_options") or [])
        approved=audit_approved()
        account_private=("PUBLIC_TO_EVERYONE" not in options and "FOLLOWER_OF_CREATOR" in options)
        if not approved and not account_private:
            return self.js(400,{"error":"unaudited_private_account_required"})
        if "SELF_ONLY" not in options:
            return self.js(400,{"error":"self_only_not_available","allowed":options})
        max_sec=int(creator.get("max_video_post_duration_sec") or 0)
        if max_sec and duration>max_sec:
            return self.js(400,{"error":"duration_not_allowed","max_sec":max_sec,"duration":duration})

        init_payload={
            "post_info":{
                "title":"",
                "privacy_level":"SELF_ONLY",
                "disable_comment":True,
                "disable_duet":True,
                "disable_stitch":True,
                "brand_content_toggle":False,
                "brand_organic_toggle":False
            },
            "source_info":{
                "source":"FILE_UPLOAD",
                "video_size":len(video),
                "chunk_size":len(video),
                "total_chunk_count":1
            }
        }
        print("PRIVATE_TEST stage=direct_post_init", flush=True)
        st,init=api_json_post(DIRECT_POST_INIT_URL,sess["access_token"],init_payload)
        ierr=(init.get("error") or {}) if isinstance(init,dict) else {}
        data=(init.get("data") or {}) if isinstance(init,dict) else {}
        print(f"PRIVATE_TEST init_http={st} code={ierr.get('code')}", flush=True)
        if not (st==200 and ierr.get("code")=="ok"):
            safe=html.escape(json.dumps({"http_status":st,"provider":ierr},ensure_ascii=False,indent=2))
            return self.send_html(502,page("TikTok init failed",f"<div class='card'><h1>فشل تهيئة Direct Post</h1><pre class='status'>{safe}</pre></div>"))

        upload_url=str(data.get("upload_url") or "")
        publish_id=str(data.get("publish_id") or "")
        if not upload_url or not publish_id:
            return self.js(502,{"error":"missing_upload_target"})
        req=urllib.request.Request(
            upload_url,data=video,
            headers={"Content-Type":"video/mp4","Content-Length":str(len(video)),"Content-Range":f"bytes 0-{len(video)-1}/{len(video)}"},
            method="PUT",
        )
        print("PRIVATE_TEST stage=binary_upload", flush=True)
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                upload_status=r.status
                r.read()
        except urllib.error.HTTPError as e:
            upload_status=e.code
            e.read()
        except Exception:
            return self.js(502,{"error":"upload_unreachable"})
        print(f"PRIVATE_TEST upload_http={upload_status}", flush=True)
        if not (200<=upload_status<300):
            return self.js(502,{"error":"binary_upload_failed","http_status":upload_status})

        with _LOCK:
            sess["last_publish_id"]=publish_id
            sess["updated_at"]=int(time.time())

        target="/private-test?publish_id="+urllib.parse.quote(publish_id,safe="")
        return self.redirect(target)

    def post_video(self,p):
        print("POST_STAGE received /api/post", flush=True)
        sid,sess=self.get_session()
        if not sess or not sess.get("access_token"):
            return self.js(401,{"error":"not_authorized"})
        if self.headers.get("X-CSRF-Token","")!=sess.get("csrf",""):
            return self.js(403,{"error":"csrf_failed"})
        q=urllib.parse.parse_qs(p.query,keep_blank_values=True)
        if q.get("consent",["false"])[0]!="true":
            return self.js(400,{"error":"explicit_consent_required"})
        try: length=int(self.headers.get("Content-Length","0"))
        except Exception: length=0
        if length<=0 or length>MAX_UPLOAD_BYTES:
            return self.js(400,{"error":"invalid_file_size","max_bytes":MAX_UPLOAD_BYTES})
        ctype=self.headers.get("Content-Type","")
        if ctype!="video/mp4":
            return self.js(400,{"error":"mp4_required"})
        title=q.get("title",[""])[0][:2200]
        privacy=q.get("privacy",[""])[0]
        allow_comment=q.get("allow_comment",["false"])[0]=="true"
        allow_duet=q.get("allow_duet",["false"])[0]=="true"
        allow_stitch=q.get("allow_stitch",["false"])[0]=="true"

        print(f"POST_STAGE reading_body length={length}", flush=True)
        video=self.rfile.read(length)
        print(f"POST_STAGE body_read bytes={len(video)}", flush=True)
        duration=mp4_duration_seconds(video)
        if duration<=0:
            return self.js(400,{"error":"invalid_mp4_or_duration_unreadable"})
        print("POST_STAGE querying_creator", flush=True)
        ok,status,creator,err=query_creator(sess["access_token"])
        print(f"POST_STAGE creator_result ok={ok} http={status}", flush=True)
        if not ok:
            return self.js(502,{"error":"creator_info_failed","provider_code":err.get("code"),"http_status":status})
        options=list(creator.get("privacy_level_options") or [])
        approved=audit_approved()
        account_private=("PUBLIC_TO_EVERYONE" not in options and "FOLLOWER_OF_CREATOR" in options)
        max_sec=int(creator.get("max_video_post_duration_sec") or 0)
        if not approved and not account_private:
            return self.js(400,{"error":"unaudited_private_account_required"})
        if not approved and privacy!="SELF_ONLY":
            return self.js(400,{"error":"unaudited_self_only_required"})
        if privacy not in options:
            return self.js(400,{"error":"privacy_not_allowed","allowed":options})
        if duration<=0 or (max_sec and duration>max_sec):
            return self.js(400,{"error":"duration_not_allowed","max_sec":max_sec})
        if creator.get("comment_disabled") and allow_comment:
            return self.js(400,{"error":"comments_disabled_by_creator"})
        if creator.get("duet_disabled") and allow_duet:
            return self.js(400,{"error":"duet_disabled_by_creator"})
        if creator.get("stitch_disabled") and allow_stitch:
            return self.js(400,{"error":"stitch_disabled_by_creator"})

        post_info={
            "title":title,
            "privacy_level":privacy,
            "disable_comment":not allow_comment,
            "disable_duet":not allow_duet,
            "disable_stitch":not allow_stitch,
            "brand_content_toggle":False,
            "brand_organic_toggle":False,
        }
        init_payload={
            "post_info":post_info,
            "source_info":{"source":"FILE_UPLOAD","video_size":length,"chunk_size":length,"total_chunk_count":1},
        }
        print("POST_STAGE initializing_direct_post", flush=True)
        st,init=api_json_post(DIRECT_POST_INIT_URL,sess["access_token"],init_payload)
        print(f"POST_STAGE init_result http={st} code={((init.get('error') or {}).get('code') if isinstance(init,dict) else 'invalid')}", flush=True)
        ierr=(init.get("error") or {}) if isinstance(init,dict) else {}
        data=(init.get("data") or {}) if isinstance(init,dict) else {}
        if not (st==200 and ierr.get("code")=="ok"):
            return self.js(502,{"error":"direct_post_init_failed","provider":ierr,"http_status":st})
        upload_url=str(data.get("upload_url") or "")
        publish_id=str(data.get("publish_id") or "")
        if not upload_url or not publish_id:
            return self.js(502,{"error":"missing_upload_target"})

        print("POST_STAGE uploading_binary", flush=True)
        req=urllib.request.Request(
            upload_url,data=video,
            headers={"Content-Type":"video/mp4","Content-Length":str(length),"Content-Range":f"bytes 0-{length-1}/{length}"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req,timeout=60) as r:
                upload_status=r.status; r.read()
        except urllib.error.HTTPError as e:
            upload_status=e.code; e.read()
        except Exception:
            return self.js(502,{"error":"upload_unreachable"})
        print(f"POST_STAGE upload_result http={upload_status}", flush=True)
        if not (200<=upload_status<300):
            return self.js(502,{"error":"binary_upload_failed","http_status":upload_status})
        with _LOCK:
            sess["last_publish_id"]=publish_id; sess["updated_at"]=int(time.time())
        return self.js(201,{"ok":True,"publish_id":publish_id,"privacy_requested":privacy,"public_client_approved":approved})

    def upload_draft(self,p):
        sid,sess=self.get_session()
        if not sess or not sess.get("access_token"):
            return self.js(401,{"error":"not_authorized"})
        if self.headers.get("X-CSRF-Token","")!=sess.get("csrf",""):
            return self.js(403,{"error":"csrf_failed"})
        q=urllib.parse.parse_qs(p.query,keep_blank_values=True)
        if q.get("consent",["false"])[0]!="true":
            return self.js(400,{"error":"explicit_consent_required"})
        try: length=int(self.headers.get("Content-Length","0"))
        except Exception: length=0
        if length<=0 or length>MAX_UPLOAD_BYTES:
            return self.js(400,{"error":"invalid_file_size","max_bytes":MAX_UPLOAD_BYTES})
        if self.headers.get("Content-Type","")!="video/mp4":
            return self.js(400,{"error":"mp4_required"})
        video=self.rfile.read(length)
        duration=mp4_duration_seconds(video)
        if duration<=0:
            return self.js(400,{"error":"invalid_mp4_or_duration_unreadable"})
        ok,status,creator,err=query_creator(sess["access_token"])
        if not ok:
            return self.js(502,{"error":"creator_info_failed","provider_code":err.get("code"),"http_status":status})
        max_sec=int(creator.get("max_video_post_duration_sec") or 0)
        if max_sec and duration>max_sec:
            return self.js(400,{"error":"duration_not_allowed","max_sec":max_sec})

        init_payload={
            "source_info":{
                "source":"FILE_UPLOAD",
                "video_size":length,
                "chunk_size":length,
                "total_chunk_count":1
            }
        }
        print("DRAFT_STAGE init", flush=True)
        st,init=api_json_post(UPLOAD_DRAFT_INIT_URL,sess["access_token"],init_payload)
        ierr=(init.get("error") or {}) if isinstance(init,dict) else {}
        data=(init.get("data") or {}) if isinstance(init,dict) else {}
        print(f"DRAFT_STAGE init_http={st} code={ierr.get('code')}", flush=True)
        if not (st==200 and ierr.get("code")=="ok"):
            return self.js(502,{"error":"draft_init_failed","provider":ierr,"http_status":st})
        upload_url=str(data.get("upload_url") or "")
        publish_id=str(data.get("publish_id") or "")
        if not upload_url or not publish_id:
            return self.js(502,{"error":"missing_upload_target"})
        req=urllib.request.Request(
            upload_url,data=video,
            headers={"Content-Type":"video/mp4","Content-Length":str(length),"Content-Range":f"bytes 0-{length-1}/{length}"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req,timeout=60) as r:
                upload_status=r.status; r.read()
        except urllib.error.HTTPError as e:
            upload_status=e.code; e.read()
        except Exception:
            return self.js(502,{"error":"upload_unreachable"})
        print(f"DRAFT_STAGE upload_http={upload_status}", flush=True)
        if not (200<=upload_status<300):
            return self.js(502,{"error":"binary_upload_failed","http_status":upload_status})
        with _LOCK:
            sess["last_draft_publish_id"]=publish_id; sess["updated_at"]=int(time.time())
        return self.js(201,{"ok":True,"publish_id":publish_id,"mode":"draft_to_tiktok_inbox"})

    def status_api(self,q):
        sid,sess=self.get_session()
        if not sess or not sess.get("access_token"):
            return self.js(401,{"error":"not_authorized"})
        publish_id=q.get("publish_id",[""])[0]
        if not publish_id:
            return self.js(400,{"error":"publish_id_required"})
        st,payload=api_json_post(STATUS_URL,sess["access_token"],{"publish_id":publish_id})
        return self.js(st if st else 502,payload)

if __name__=="__main__":
    ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
