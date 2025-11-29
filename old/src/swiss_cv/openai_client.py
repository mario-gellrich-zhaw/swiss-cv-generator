from .openai_compat import ChatCompletion as ChatCompletionCompat
# Use compatibility shim via ChatCompletionCompat.create(...)
    from openai.error import RateLimitError, ServiceUnavailableError, APIError, Timeout
except Exception:
    _openai_pkg = None
    RateLimitError = ServiceUnavailableError = APIError = Timeout = Exception

# Settings from environment
_DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
_API_KEY = os.getenv("OPENAI_API_KEY") or None

# Where to look for local prompt templates
TEMPLATE_DIR = os.path.join(os.getcwd(), "templates", "prompts")

class OpenAIClient:
    def __init__(self, api_key: Optional[str] = None, model: str = _DEFAULT_MODEL,
                 max_retries: int = 5, backoff_base: float = 0.5, max_backoff: float = 20.0):
        self.api_key = api_key or _API_KEY
        self.model = model
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff

        # If we have the real package, configure the API key there
        if _openai_pkg and self.api_key:
            try:
                _openai_pkg.api_key = self.api_key
            except Exception:
                pass

    def _backoff_sleep(self, attempt: int):
        # exponential backoff with jitter
        base = self.backoff_base * (2 ** attempt)
        delay = min(self.max_backoff, base) * (0.5 + random.random() * 0.5)
        time.sleep(delay)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 256, timeout: Optional[int] = 30) -> str:
        """
        Wrapper around ChatCompletion-like API. `messages` is a list of {'role': 'user'|'system'|'assistant', 'content': '...'}.
        Returns assistant content string. On persistent failures or missing API key, raises or falls back to template (caller can call fallback).
        """
        # If OpenAI package missing or no api key, raise so caller can fallback
        if not _openai_pkg or not self.api_key:
            raise RuntimeError("OpenAI package or API key not available")

        last_exc = None
        for attempt in range(self.max_retries):
            try:
                resp = _openai_pkg.ChatCompletion.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout
                )
                # compatible with openai responses: try to get the first choice content
                choices = resp.get("choices") if isinstance(resp, dict) else getattr(resp, "choices", None)
                if choices:
                    text = choices[0]["message"]["content"] if isinstance(choices[0], dict) else choices[0].message.content
                    return text.strip()
                # fallback: try text attribute
                return str(resp).strip()
            except (RateLimitError, ServiceUnavailableError, APIError, Timeout) as e:
                last_exc = e
                # exponential backoff
                self._backoff_sleep(attempt)
                continue
            except Exception as e:
                # non-transient error; break and rethrow
                last_exc = e
                break

        # exhausted retries
        raise last_exc if last_exc is not None else RuntimeError("OpenAI request failed")

    # convenience wrapper for single-user prompt
    def prompt(self, prompt_text: str, system: Optional[str] = None, temperature: float = 0.7,
               max_tokens: int = 256, timeout: Optional[int] = 30) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt_text})
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)

    # safe call that returns fallback_text if OpenAI not available or fails
    def prompt_with_fallback(self, prompt_text: str, fallback_template: Optional[str] = None,
                             fallback_ctx: Optional[Dict[str, Any]] = None, language: str = "de",
                             system: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 256) -> str:
        try:
            return self.prompt(prompt_text, system=system, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            # fallback to local template if provided
            if fallback_template:
                try:
                    return self._render_local_template(fallback_template, language, fallback_ctx or {})
                except Exception:
                    pass
            # last-resort: return prompt truncated
            return (fallback_ctx or {}).get("fallback_text") or prompt_text[:min(400, len(prompt_text))]

    def _render_local_template(self, template_name: str, language: str, ctx: Dict[str, Any]) -> str:
        """
        Load a local template file templates/prompts/{language}/{template_name}.txt and format using ctx.
        Template uses Python str.format() placeholders like {name}, {years_experience}, etc.
        """
        # try a few language fallbacks
        candidates = [
            os.path.join(TEMPLATE_DIR, language, f"{template_name}.txt"),
            os.path.join(TEMPLATE_DIR, language.split("-")[0], f"{template_name}.txt"),
            os.path.join(TEMPLATE_DIR, "de", f"{template_name}.txt"),
            os.path.join(TEMPLATE_DIR, "en", f"{template_name}.txt"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        tpl = fh.read()
                    return tpl.format(**ctx)
                except Exception:
                    # If formatting fails, try to return template raw
                    return tpl
        # no template found
        raise FileNotFoundError(f"No template found for {template_name} @ {TEMPLATE_DIR}")

    # high-level helper for persona summary generation
    def generate_summary(self, persona: Dict[str, Any], language: str = "de", template: str = "summary") -> str:
        """
        persona: dict with keys like first_name, last_name, title, years_experience, industry, language, canton...
        language: 'de'|'fr'|'it' etc.
        template: template name to use for fallback (file {template}.txt under templates/prompts/<lang>/)
        """
        # Build a compact prompt from persona
        name = persona.get("first_name", "") + " " + persona.get("last_name", "")
        title = persona.get("title", "") or persona.get("role", "")
        years = persona.get("years_experience", persona.get("experience_years", ""))
        industry = persona.get("industry", "")
        lang_tag = language or persona.get("primary_language", "de")
        prompt = f"Write a professional one-paragraph CV summary in {lang_tag} for {name}, {title}, {years} years experience in {industry}. Keep it concise and Swiss-appropriate."

        # context we can pass to formatting fallback
        ctx = {
            "first_name": persona.get("first_name", ""),
            "last_name": persona.get("last_name", ""),
            "name": name.strip(),
            "title": title,
            "years_experience": years,
            "industry": industry,
            "canton": persona.get("canton", ""),
            "language": lang_tag
        }

        # try OpenAI then fallback to local template
        return self.prompt_with_fallback(prompt, fallback_template=template, fallback_ctx=ctx, language=lang_tag)

# Single shared client for easy import
client = OpenAIClient()




