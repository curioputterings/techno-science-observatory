"""Minimal local LLM client (stdlib only — no SDK, no pip needed).

Companion to gemini_client.py: same call-and-parse discipline (load .env,
defensive JSON extraction, no dependency beyond the standard library) but talks
to a locally-running LM Studio server instead of the cloud, so this tier is
free. Used by ats/classify.py to fill the residual gap the regex classifier
can't resolve confidently.

Local models here may be hybrid-reasoning (spend most of the token budget on
internal chain-of-thought before the actual JSON answer) -- max_tokens defaults
generously and content falls back to reasoning_content, mirroring the same
lesson learned wiring this pattern into ai_work_recomp.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def load_env(path: Path | None = None) -> dict:
    env: dict[str, str] = {}
    p = path or (ROOT / ".env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


_ENV = load_env()
LOCAL_LLM_URL = _ENV.get("LOCAL_LLM_URL", "http://localhost:1234/v1/chat/completions")
LOCAL_MODEL = _ENV.get("LOCAL_MODEL", "google/gemma-4-e4b")
LOCAL_LLM_TIMEOUT = float(_ENV.get("LOCAL_LLM_TIMEOUT", "120"))
# How many NEW (not-yet-cached) postings ats/classify.py will escalate to the
# local model in a single process run. Real registries can carry thousands of
# open postings with a ~50% escalation rate (each call takes tens of seconds),
# so an uncapped run can take many hours; the cache (classify_cache.db) means
# postings skipped this run due to the cap get picked up on a later run instead
# of being re-attempted from scratch, so the backlog drains over a few weeks.
ESCALATION_CAP_PER_RUN = int(_ENV.get("LLM_ESCALATION_CAP", "250"))


class LocalLLMUnavailable(RuntimeError):
    """Raised on any connection problem — caller decides whether to skip or
    fall back (e.g. LM Studio not running on this box)."""


def _extract_json(text: str):
    candidate = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", candidate, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    raise ValueError("No JSON found in local model response")


def structured(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.0,
    timeout: float | None = None,
) -> dict:
    """Call the local LM Studio server and return parsed JSON.

    Raises LocalLLMUnavailable on any connection problem, ValueError on
    malformed output. max_tokens defaults high: a hybrid-reasoning local model
    can burn hundreds of tokens on internal thought before the actual JSON
    answer, and a tight cap truncates mid-thought with no answer at all.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model or LOCAL_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        LOCAL_LLM_URL, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or LOCAL_LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise LocalLLMUnavailable(f"local LLM unreachable: {exc!r}") from exc

    message = data["choices"][0]["message"]
    content = message.get("content") or message.get("reasoning_content") or ""
    return _extract_json(content)
