"""strategist_client.py — Talks to a local Anthropic-compatible proxy."""
from __future__ import annotations
import json, os
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

@dataclass
class StrategistResponse:
    worker_task: str = ""
    rationale: str = ""
    expected_artifacts: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    risk_notes: str = ""

@dataclass
class StrategistConfig:
    provider: str = "anthropic_compatible"
    base_url: str = "http://127.0.0.1:1234"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.2
    max_tokens: int = 4096

def call_strategist(config: StrategistConfig, system_prompt: str, goal: str, iteration: int, max_iters: int, history: list[dict] | None = None) -> StrategistResponse:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "sk-dummy")
    msg = f"{system_prompt}\n\n## Goal\n{goal}\n\n## Iteration {iteration+1} of {max_iters}\n\n"
    if history:
        msg += "## Previous iterations (last 5):\n"
        for h in history[-5:]: msg += f"- Iter {h.get('iteration','?')}: task={h.get('worker_task','')[:80]}, gate={h.get('gate_result','UNKNOWN')}\n"
    msg += "\nRespond with valid JSON only. Keys: worker_task, rationale, expected_artifacts, success_criteria, risk_notes\n"
    payload = {"model": config.model, "messages": [{"role": "user", "content": msg}, {"role": "assistant", "content": '{"'}], "max_tokens": config.max_tokens, "temperature": config.temperature}
    url = config.base_url.rstrip("/")
    for ep in ["/v1/messages", "/v1/chat/completions", "/completions"]:
        try:
            body = json.dumps(payload).encode("utf-8")
            req = Request(url+ep, data=body, headers={"Content-Type":"application/json","Accept":"application/json","x-api-key":api_key,"Authorization":f"Bearer {api_key}"}, method="POST")
            with urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
            return _parse(resp, ep)
        except: continue
    raise RuntimeError(f"Strategist unreachable at {url}")

def _parse(resp: dict, ep: str) -> StrategistResponse:
    txt = ""
    if ep == "/v1/messages":
        for b in resp.get("content", []):
            if b.get("type") == "text": txt += b.get("text","")
    elif ep == "/v1/chat/completions":
        txt = (resp.get("choices",[{}])[0].get("message",{}) or {}).get("content","")
    else: txt = resp.get("text","") or resp.get("completion","") or str(resp)
    txt = txt.strip()
    if "```json" in txt: txt = txt.split("```json",1)[1].split("```",1)[0]
    elif "```" in txt: txt = txt.split("```",1)[1].split("```",1)[0]
    try: d = json.loads(txt)
    except json.JSONDecodeError:
        s, e = txt.find("{"), txt.rfind("}")
        if s >= 0 and e > s:
            try: d = json.loads(txt[s:e+1])
            except: d = {"worker_task": txt[:2048]}
        else: d = {"worker_task": txt[:2048]}
    return StrategistResponse(worker_task=d.get("worker_task","") or str(d), rationale=d.get("rationale",""), expected_artifacts=d.get("expected_artifacts",[]), success_criteria=d.get("success_criteria",[]), risk_notes=d.get("risk_notes",""))
