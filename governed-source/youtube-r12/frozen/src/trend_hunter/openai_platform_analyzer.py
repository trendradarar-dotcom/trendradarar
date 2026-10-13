from __future__ import annotations
import json, os
from typing import Any, Callable
import urllib.error, urllib.request

OPENAI_PLATFORM_ANALYZER_VERSION = "1.0.0"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"

def _redact_secrets(value: Any) -> Any:
    markers=("api_key","apikey","authorization","bearer","credential","password","secret","token")
    if isinstance(value,dict):
        return {str(k):("[REDACTED]" if any(m in str(k).lower() for m in markers) else _redact_secrets(v)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [_redact_secrets(v) for v in value]
    return value

def _extract_output_text(response: dict[str,Any]) -> str:
    direct=response.get("output_text")
    if isinstance(direct,str) and direct.strip():
        return direct.strip()
    pieces=[]
    for item in response.get("output") or []:
        if not isinstance(item,dict) or item.get("type")!="message":
            continue
        for part in item.get("content") or []:
            if isinstance(part,dict) and part.get("type")=="output_text" and isinstance(part.get("text"),str):
                pieces.append(part["text"])
    text="\n".join(pieces).strip()
    if not text:
        raise RuntimeError("OpenAI Responses result contained no output text")
    return text

def _parse_json_object(text: str) -> dict[str,Any]:
    s=text.strip()
    if s.startswith("```"):
        a=s.find("\n"); b=s.rfind("```")
        if a>=0 and b>a: s=s[a+1:b].strip()
    try:
        obj=json.loads(s)
    except json.JSONDecodeError:
        a=s.find("{"); b=s.rfind("}")
        if a<0 or b<=a: raise RuntimeError("OpenAI platform review did not return a JSON object")
        obj=json.loads(s[a:b+1])
    if not isinstance(obj,dict): raise RuntimeError("OpenAI platform review JSON root must be an object")
    return obj

class OpenAIResponsesAnalyzer:
    name="openai_responses"
    def __init__(self,*,api_key:str|None=None,model:str|None=None,endpoint:str=DEFAULT_ENDPOINT,timeout:int=90,http_post:Callable|None=None):
        self.api_key=(api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        self.model=(model or os.getenv("TREND_HUNTER_PLATFORM_REVIEW_MODEL") or DEFAULT_MODEL).strip()
        self.endpoint=endpoint; self.timeout=timeout; self._http_post=http_post

    def _post(self,body:dict[str,Any])->dict[str,Any]:
        if not self.api_key: raise RuntimeError("OPENAI_API_KEY is not configured")
        headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json; charset=utf-8","Accept":"application/json"}
        raw=json.dumps(body,ensure_ascii=False,separators=(",",":")).encode("utf-8")
        if self._http_post:
            result=self._http_post(self.endpoint,headers,raw,self.timeout)
            if not isinstance(result,dict): raise RuntimeError("OpenAI transport returned a non-object response")
            return result
        req=urllib.request.Request(self.endpoint,data=raw,headers=headers,method="POST")
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail=exc.read().decode("utf-8",errors="replace")
            raise RuntimeError(f"OpenAI Responses HTTP {exc.code}: {detail[:1200]}") from exc

    def analyze(self,*,platform:str,creative:dict[str,Any],rules:list[dict[str,Any]])->dict[str,Any]:
        if not isinstance(creative,dict): raise RuntimeError("creative evidence must be an object")
        keep=("rule_id","title","summary","description","source_url","official_source_url")
        governed=[{k:r[k] for k in keep if k in r} for r in rules]
        instructions=(
            "You are TrendHunter's automated platform-policy reviewer. Evaluate ONLY supplied evidence against supplied governed rules. "
            "Saudi legal review is separate and human; do not apply Saudi law here. Never infer unseen image, audio, video, context or intent. "
            "For every rule return PASS, BLOCK, HOLD, or NOT_APPLICABLE. BLOCK only when supplied evidence clearly establishes a violation. "
            "PASS only when supplied evidence is sufficient and no violation is found. HOLD whenever evidence is missing, ambiguous or incomplete. "
            "Confidence is 0..1. Set review_complete=true only if every governed rule is resolved without HOLD and all relevant modalities needed "
            "for those judgments are actually represented in supplied evidence. Return JSON only with review_complete, reviewed_modalities, rules; "
            "rules must contain exactly the supplied rule_ids with rule_id,status,confidence,reason."
        )
        payload={"platform":platform,"analyzer_version":OPENAI_PLATFORM_ANALYZER_VERSION,"creative_evidence":_redact_secrets(creative),"governed_rules":governed}
        response=self._post({"model":self.model,"instructions":instructions,"input":json.dumps(payload,ensure_ascii=False,separators=(",",":"))})
        if response.get("status")=="incomplete": raise RuntimeError("OpenAI Responses review was incomplete")
        result=_parse_json_object(_extract_output_text(response))
        result["_provider"]={"provider":"openai","model":self.model,"response_id":response.get("id"),"analyzer_version":OPENAI_PLATFORM_ANALYZER_VERSION}
        return result