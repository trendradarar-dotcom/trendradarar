import base64, hashlib, json, os, secrets, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AUTH_URL="https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL="https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL="https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
UPLOAD_INIT_URL="https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
DEFAULT_SCOPES="user.info.basic,video.upload,video.publish"
TTL=600
_STATES={}
_TOKENS={}
_LAST_TEST={}
_LOCK=threading.Lock()
DEMO_B64_PATH=Path(__file__).with_name("demo_video.b64")

def cfg(name):
    return str(os.environ.get(name,"")).strip()

def configured():
    return all((cfg("TIKTOK_CLIENT_KEY"),cfg("TIKTOK_CLIENT_SECRET"),cfg("TIKTOK_REDIRECT_URI")))

def fingerprint(v):
    return hashlib.sha256(v.encode()).hexdigest() if v else ""

def api_json_post(url, token, payload=None, timeout=20):
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
            raw=r.read()
            status=r.status
    except urllib.error.HTTPError as e:
        raw=e.read()
        status=e.code
    try:
        parsed=json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        parsed={"raw_unparsed":True}
    return status, parsed

def load_demo_video():
    raw=DEMO_B64_PATH.read_text(encoding="utf-8").strip()
    return base64.b64decode(raw)

def run_private_draft_test(access_token):
    result={"creator_info_ok":False,"draft_upload_initialized":False,"draft_binary_uploaded":False}
    status,creator=api_json_post(CREATOR_INFO_URL,access_token,{})
    result["creator_info_http_status"]=status
    err=(creator.get("error") or {}) if isinstance(creator,dict) else {}
    data=(creator.get("data") or {}) if isinstance(creator,dict) else {}
    if status==200 and err.get("code")=="ok":
        result["creator_info_ok"]=True
        result["creator_username"]=str(data.get("creator_username") or "")
        result["creator_nickname"]=str(data.get("creator_nickname") or "")
        result["privacy_level_options"]=list(data.get("privacy_level_options") or [])
        result["max_video_post_duration_sec"]=data.get("max_video_post_duration_sec")
    else:
        result["creator_info_error_code"]=str(err.get("code") or f"http_{status}")
        return result

    video=load_demo_video()
    size=len(video)
    init_payload={
        "source_info":{
            "source":"FILE_UPLOAD",
            "video_size":size,
            "chunk_size":size,
            "total_chunk_count":1,
        }
    }
    status,init=api_json_post(UPLOAD_INIT_URL,access_token,init_payload)
    result["draft_init_http_status"]=status
    err=(init.get("error") or {}) if isinstance(init,dict) else {}
    data=(init.get("data") or {}) if isinstance(init,dict) else {}
    if not (status==200 and err.get("code")=="ok"):
        result["draft_init_error_code"]=str(err.get("code") or f"http_{status}")
        return result

    upload_url=str(data.get("upload_url") or "")
    publish_id=str(data.get("publish_id") or "")
    if not upload_url or not publish_id:
        result["draft_init_error_code"]="missing_upload_url_or_publish_id"
        return result
    result["draft_upload_initialized"]=True
    result["publish_id"]=publish_id

    req=urllib.request.Request(
        upload_url,
        data=video,
        headers={
            "Content-Type":"video/mp4",
            "Content-Length":str(size),
            "Content-Range":f"bytes 0-{size-1}/{size}",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            upload_status=r.status
            r.read()
    except urllib.error.HTTPError as e:
        upload_status=e.code
        e.read()
    except Exception:
        result["draft_upload_error_code"]="upload_unreachable"
        return result
    result["draft_upload_http_status"]=upload_status
    result["draft_binary_uploaded"]=200 <= upload_status < 300
    if not result["draft_binary_uploaded"]:
        result["draft_upload_error_code"]=f"http_{upload_status}"
    return result

class Handler(BaseHTTPRequestHandler):
    server_version="TrendRadarTikTokOAuth/1.1"

    def log_message(self,fmt,*args):
        path=urllib.parse.urlsplit(self.path).path
        print(f"{self.address_string()} - {self.command} {path} - {fmt % args}")

    def end_headers(self):
        for k,v in {
            "Cache-Control":"no-store","Pragma":"no-cache",
            "X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY",
            "Referrer-Policy":"no-referrer",
            "Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        }.items(): self.send_header(k,v)
        super().end_headers()

    def js(self,status,payload):
        body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redir(self,url):
        self.send_response(302); self.send_header("Location",url)
        self.send_header("Content-Length","0"); self.end_headers()

    def do_GET(self):
        p=urllib.parse.urlsplit(self.path)
        q=urllib.parse.parse_qs(p.query,keep_blank_values=True)
        if p.path=="/":
            return self.js(200,{"service":"Trend Radar TikTok OAuth","status":"ready" if configured() else "configuration_required","publication_authority":False})
        if p.path=="/health":
            return self.js(200,{"ok":True,"configured":configured()})
        if p.path=="/auth/tiktok/start":
            return self.start()
        if p.path=="/auth/tiktok/callback":
            return self.callback(q)
        if p.path=="/auth/tiktok/status":
            with _LOCK:
                t=dict(_TOKENS.get("owner") or {})
                test=dict(_LAST_TEST)
            return self.js(200,{
                "configured":configured(),
                "authorized":bool(t),
                "scope":t.get("scope",""),
                "publication_authority":False,
                "token_plaintext_exposed":False,
                "private_test":test,
            })
        return self.js(404,{"error":"not_found"})

    def start(self):
        if not configured(): return self.js(503,{"error":"service_not_configured"})
        now=int(time.time())
        with _LOCK:
            for s,ts in list(_STATES.items()):
                if now-ts>TTL: _STATES.pop(s,None)
            state=secrets.token_urlsafe(32)
            _STATES[state]=now
        params={
            "client_key":cfg("TIKTOK_CLIENT_KEY"),
            "response_type":"code",
            "scope":cfg("TIKTOK_SCOPES") or DEFAULT_SCOPES,
            "redirect_uri":cfg("TIKTOK_REDIRECT_URI"),
            "state":state,
            "disable_auto_auth":"1",
        }
        return self.redir(AUTH_URL+"?"+urllib.parse.urlencode(params))

    def callback(self,q):
        if not configured(): return self.js(503,{"error":"service_not_configured"})
        if q.get("error"):
            return self.js(400,{"error":"authorization_denied_or_failed","provider_error":q.get("error",[""])[0]})
        state=q.get("state",[""])[0]
        code=q.get("code",[""])[0]
        now=int(time.time())
        with _LOCK:
            started=_STATES.pop(state,0) if state else 0
        if not state or not started: return self.js(400,{"error":"oauth_state_mismatch"})
        if now-int(started)>TTL: return self.js(400,{"error":"oauth_state_expired"})
        if not code: return self.js(400,{"error":"authorization_code_missing"})

        data=urllib.parse.urlencode({
            "client_key":cfg("TIKTOK_CLIENT_KEY"),
            "client_secret":cfg("TIKTOK_CLIENT_SECRET"),
            "code":code,
            "grant_type":"authorization_code",
            "redirect_uri":cfg("TIKTOK_REDIRECT_URI"),
        }).encode()
        req=urllib.request.Request(
            TOKEN_URL,
            data=data,
            headers={"Content-Type":"application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=20) as r:
                status=r.status
                raw=r.read()
        except urllib.error.HTTPError as e:
            return self.js(502,{"error":"token_exchange_failed","status":e.code})
        except Exception:
            return self.js(502,{"error":"token_exchange_unreachable"})
        if status!=200:
            return self.js(502,{"error":"token_exchange_failed","status":status})
        try:
            payload=json.loads(raw.decode())
        except Exception:
            return self.js(502,{"error":"token_exchange_invalid_json"})

        a=str(payload.get("access_token","")).strip()
        r=str(payload.get("refresh_token","")).strip()
        oid=str(payload.get("open_id","")).strip()
        scope=str(payload.get("scope","")).strip()
        exp=int(payload.get("expires_in",0) or 0)
        if not a or not r or not oid or exp<=0:
            return self.js(502,{"error":"token_exchange_incomplete"})

        with _LOCK:
            _TOKENS["owner"]={
                "access_token":a,
                "refresh_token":r,
                "open_id":oid,
                "scope":scope,
                "expires_at":now+exp,
                "access_token_sha256":fingerprint(a),
                "refresh_token_sha256":fingerprint(r),
            }

        private_test=run_private_draft_test(a)
        with _LOCK:
            _LAST_TEST.clear()
            _LAST_TEST.update(private_test)

        return self.js(200,{
            "authorized":True,
            "provider":"tiktok",
            "scope":scope,
            "token_plaintext_exposed":False,
            "publication_authority":False,
            "private_test":private_test,
        })

if __name__=="__main__":
    ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
