import os, time, random
from typing import List, Dict, Optional, Any

try:
    import openai as _openai_pkg
    from openai.error import RateLimitError, ServiceUnavailableError, APIError, Timeout
except Exception:
    _openai_pkg = None
    RateLimitError = ServiceUnavailableError = APIError = Timeout = Exception

TEMPLATE_DIR = os.path.join(os.getcwd(), 'templates', 'prompts')

class OpenAIWrapper:
    def __init__(self, api_key: Optional[str]=None, model: str=None, max_retries: int=5):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
        self.max_retries = max_retries
        if _openai_pkg and self.api_key:
            _openai_pkg.api_key = self.api_key

    def _backoff(self, attempt:int):
        base = 0.5 * (2 ** attempt)
        delay = min(20, base) * (0.5 + random.random()*0.5)
        time.sleep(delay)

    def chat(self, messages: List[Dict[str,str]], temperature: float=0.7, max_tokens: int=256) -> str:
        if not _openai_pkg or not self.api_key:
            raise RuntimeError('OpenAI SDK or API key not available')
        last = None
        for attempt in range(self.max_retries):
            try:
                resp = _openai_pkg.ChatCompletion.create(model=self.model, messages=messages, temperature=temperature, max_tokens=max_tokens)
                choices = getattr(resp, 'choices', None) or resp.get('choices', None)
                if choices:
                    # standard shape: choices[0].message.content
                    c0 = choices[0]
                    if isinstance(c0, dict):
                        return c0['message']['content'].strip()
                    else:
                        return getattr(c0, 'message').content.strip()
                return str(resp).strip()
            except (RateLimitError, ServiceUnavailableError, APIError, Timeout) as e:
                last = e
                self._backoff(attempt)
                continue
            except Exception as e:
                last = e
                break
        raise last or RuntimeError('OpenAI call failed')

    def prompt_with_fallback(self, prompt_text: str, template_name: Optional[str]=None, ctx: Optional[Dict[str,Any]]=None, language: str='de') -> str:
        ctx = ctx or {}
        # Try the API
        try:
            msgs = [{"role":"user","content":prompt_text}]
            return self.chat(msgs)
        except Exception:
            # fallback to local template
            if template_name:
                # try language-specific template
                candidates = [
                    os.path.join(TEMPLATE_DIR, language, f"{template_name}.txt"),
                    os.path.join(TEMPLATE_DIR, language.split('-')[0], f"{template_name}.txt"),
                    os.path.join(TEMPLATE_DIR, 'de', f"{template_name}.txt"),
                    os.path.join(TEMPLATE_DIR, 'en', f"{template_name}.txt")
                ]
                for p in candidates:
                    if p and os.path.exists(p):
                        try:
                            with open(p, 'r', encoding='utf-8') as fh:
                                tpl = fh.read()
                            return tpl.format(**ctx)
                        except Exception:
                            return tpl
            # last resort: return truncated prompt
            return prompt_text[:400]

# single instance
client = OpenAIWrapper()


