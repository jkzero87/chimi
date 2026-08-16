"""Self-contained LLM client for chimi. Imports NOTHING from
research.py or llm/harness — stdlib only, so this project has no
requirements.txt dependencies.
"""
import json
import re
import urllib.error
import urllib.request


def _clean_model_text(content):
    content = content or ""
    content = re.sub(r"<think>.*?</think>", " ", content, flags=re.S | re.I)
    if "</think>" in content:
        content = content.split("</think>")[-1]
    return content.strip()


def _parse_json_loose(content):
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()

    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass

    start = content.find("{")
    if start != -1:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i, ch in enumerate(content[start:], start):
            if ch == '"' and not esc:
                in_str = not in_str
            esc = ch == "\\" and not esc
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end != -1:
            candidate = content[start:end + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except ValueError:
                pass

    raise ValueError(f"could not parse JSON from model output: {content[:500]}")


def _json_or_text(content):
    cleaned = _clean_model_text(content)

    try:
        obj = _parse_json_loose(cleaned)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass

    if cleaned:
        return {
            "answer": cleaned,
            "citations": [],
            "confidence": 0.2,
            "uncertainties": "model returned non-JSON text",
            "insufficient_evidence": False,
            "raw_text": True,
        }

    return {
        "call_failed": True,
        "error": "empty model content",
        "answer": "ERROR: empty model content",
        "insufficient_evidence": True,
    }


def llm_json(port, system, user, temp=0.1, max_tokens=800, enable_thinking=False):
    url = f"http://127.0.0.1:{port}/v1/chat/completions"

    if not enable_thinking and "/no_think" not in user:
        user = user + "\n\n/no_think"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    base = {
        "model": "local",
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    payloads = [
        {**base, "response_format": {"type": "json_object"}},
        base,
    ]

    last_error = "unknown llama-server error"
    saw_empty = False

    for payload in payloads:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:800]
            last_error = f"{e.code} {e.reason}: {body}"
            if e.code == 400 and "response_format" in payload:
                continue
            raise RuntimeError(last_error)
        except (urllib.error.URLError, OSError) as e:
            last_error = str(e)
            if "response_format" in payload:
                continue
            raise RuntimeError(last_error)

        choices = data.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        content = (
            message.get("content")
            or message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        )
        content = _clean_model_text(content)

        if not content:
            saw_empty = True
            last_error = "empty model content"
            continue

        return _json_or_text(content)

    if saw_empty:
        return {
            "call_failed": True,
            "error": "empty model content after fallbacks",
            "answer": "ERROR: empty model content",
            "insufficient_evidence": True,
        }

    raise RuntimeError(last_error)
