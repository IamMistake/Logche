import json
import os
import time
import urllib.error
import urllib.request


def call(model, messages, temperature=0.0, max_tokens=400, timeout=120):
    payload = {"model": model["model"], "temperature": temperature, "max_tokens": max_tokens, "messages": messages}
    request = urllib.request.Request(model["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get(model.get("api_key_env", "OPENAI_API_KEY"), "not-needed")})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
        text = body["choices"][0]["message"]["content"]
        return text, (time.perf_counter() - started) * 1000, None
    except (OSError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return "", (time.perf_counter() - started) * 1000, str(exc)
