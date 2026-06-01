"""Minimal Gemini REST client (stdlib only — no SDK, no pip needed).

Reads GEMINI_API_KEY / GEMINI_MODEL from a local .env (gitignored). Provides
structured JSON generation via the generateContent responseSchema feature.
This is the automated Phase-2 path; it replaces the broken MCP (which was pinned
to a retired model).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


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
API_KEY = _ENV.get("GEMINI_API_KEY", "")
MODEL = _ENV.get("GEMINI_MODEL", "gemini-2.5-flash")


def ready() -> bool:
    return bool(API_KEY)


def _post(url: str, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def structured(prompt: str, schema: dict, model: str | None = None,
               temperature: float = 0.3, retries: int = 3) -> dict:
    """Return parsed JSON object conforming to `schema`."""
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing in .env")
    model = model or MODEL
    url = ENDPOINT.format(model=model, key=API_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    last_err = None
    for attempt in range(retries):
        try:
            data = _post(url, body)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            last_err = f"HTTP {e.code}: {detail}"
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as e:
            last_err = repr(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini call failed after {retries} tries: {last_err}")


# Schema-dict version of research.DOMAIN_SCHEMA (responseSchema wants a dict).
def domain_schema() -> dict:
    import taxonomy
    return {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "cells": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "country_iso": {"type": "string"},
                        "country_name": {"type": "string"},
                        "volume_band": {
                            "type": "string",
                            "enum": [b["key"] for b in taxonomy.VOLUME_BANDS.values()],
                        },
                        "skill_level": {"type": "integer"},
                        "frontier": {"type": "number"},
                        "rationale": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": taxonomy.CONFIDENCE_LEVELS},
                    },
                    "required": ["country_iso", "country_name", "volume_band",
                                 "skill_level", "frontier", "confidence"],
                },
            },
        },
        "required": ["domain", "cells"],
    }
