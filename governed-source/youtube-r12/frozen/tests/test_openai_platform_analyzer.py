import json
from trend_hunter.openai_platform_analyzer import OpenAIResponsesAnalyzer,_redact_secrets,_extract_output_text,_parse_json_object

def test_secret_redaction():
    x=_redact_secrets({"caption":"ok","api_key":"x","n":{"token":"y"}})
    assert x["caption"]=="ok" and x["api_key"]=="[REDACTED]" and x["n"]["token"]=="[REDACTED]"

def test_output_parse():
    r={"output":[{"type":"message","content":[{"type":"output_text","text":"```json\n{\"review_complete\":false}\n```"}]}]}
    assert _parse_json_object(_extract_output_text(r))["review_complete"] is False

def test_fake_responses_transport():
    seen={}
    def post(url,headers,raw,timeout):
        seen["body"]=json.loads(raw.decode())
        return {"id":"resp_test","status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":json.dumps({"review_complete":True,"reviewed_modalities":["text"],"rules":[{"rule_id":"R1","status":"PASS","confidence":0.99,"reason":"ok"}]})}]}]}
    a=OpenAIResponsesAnalyzer(api_key="sk-test",http_post=post)
    out=a.analyze(platform="youtube",creative={"caption":"hello","secret_token":"hide"},rules=[{"rule_id":"R1","title":"r"}])
    assert out["rules"][0]["status"]=="PASS"
    assert "hide" not in seen["body"]["input"]