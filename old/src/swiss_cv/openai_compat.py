# Compatibility shim to emulate a subset of openai.ChatCompletion.create()
# Delegates to swiss_cv.openai_wrapper.client.chat() for actual calls.
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
import json

# Try to import the wrapper client from a couple of likely locations
_client = None
for _p in ('swiss_cv.openai_wrapper', '.src.swiss_cv.openai_wrapper', 'src.swiss_cv.openai_wrapper'):
    try:
        mod = __import__(_p, fromlist=['client'])
        _client = getattr(mod, 'client', None)
        if _client is not None:
            break
    except Exception:
        continue

def _format_response(text: str) -> Dict[str, Any]:
    # minimal shape compatible with old code: {'choices':[{'message':{'content': text}}]}
    return {'choices': [{'message': {'content': text}}]}

class ChatCompletion:
    @staticmethod
    def create(model: Optional[str]=None, messages: Optional[List[Dict[str,str]]]=None,
               temperature: float=0.7, max_tokens: int=256, **kwargs):
        if _client is None:
            raise RuntimeError('OpenAI client wrapper not available (openai_compat failed to find wrapper)')
        # If messages is a list of dicts like [{'role':'user','content':'...'}, ...]
        if isinstance(messages, list):
            # join all content fields preserving order (old call sites typically expect a single reply)
            prompt = "\\n".join([m.get('content','') for m in messages if isinstance(m, dict)])
        elif isinstance(messages, str) or messages is None:
            prompt = messages or ""
        else:
            # fallback: try to stringify
            prompt = str(messages)
        # Delegate to wrapper.client.chat -- wrapper should return a text string
        text = _client.chat(messages=[{'role':'user','content':prompt}], temperature=temperature, max_tokens=max_tokens)
        # If wrapper returns an object with 'content', extract it
        if isinstance(text, dict) and 'content' in text:
            text = text['content']
        return _format_response(str(text))


