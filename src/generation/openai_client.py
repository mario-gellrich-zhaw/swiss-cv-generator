# src/generation/openai_client.py
"""
Centralized OpenAI client wrapper.

Supports both:
 - modern openai >= 1.0.0 API (from openai import OpenAI; client.chat.completions.create(...))
 - legacy openai 0.28.x API (openai.ChatCompletion.create(...))

Uses exponential backoff for transient errors.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any
import time
import random
import logging

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_settings

LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 1.0

# Singleton client instance
_openai_client = None
_openai_available = False
_initialized = False


def _initialize_client():
    """Initialize OpenAI client (singleton pattern)."""
    global _openai_client, _openai_available, _initialized
    
    if _initialized:
        return
    
    _initialized = True
    settings = get_settings()
    
    try:
        # Try modern client first (openai >= 1.0.0)
        try:
            from openai import OpenAI
            if settings.openai_api_key:
                _openai_client = OpenAI(api_key=settings.openai_api_key)
                _openai_available = True
                LOGGER.debug("Initialized modern OpenAI client (openai >= 1.0.0)")
        except ImportError:
            # Fallback to legacy client (openai 0.28.x)
            try:
                import openai
                if settings.openai_api_key:
                    openai.api_key = settings.openai_api_key
                    _openai_available = True
                    LOGGER.debug("Initialized legacy OpenAI client (openai 0.28.x)")
            except ImportError:
                LOGGER.warning("OpenAI package not available")
    except Exception as e:
        LOGGER.warning(f"Failed to initialize OpenAI client: {e}")


def get_openai_client():
    """Get the singleton OpenAI client instance."""
    _initialize_client()
    return _openai_client


def is_openai_available() -> bool:
    """Check if OpenAI is available."""
    _initialize_client()
    return _openai_available


def _sleep_with_backoff(attempt: int) -> None:
    """Exponential backoff with jitter."""
    backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
    jitter = random.uniform(0, backoff * 0.2)
    sleep_for = backoff + jitter
    LOGGER.debug("Backoff: sleeping %.2fs (attempt %d)", sleep_for, attempt)
    time.sleep(sleep_for)


def _is_transient_error(exc: Exception) -> bool:
    """Detect transient errors that should be retried."""
    msg = str(exc).lower()
    return any(k in msg for k in ("rate", "timeout", "temporar", "429", "timed out", "connection"))


def call_openai_chat(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 400,
    temperature: float = 0.7
) -> str:
    """
    Call the OpenAI chat completion API.
    
    Supports both modern (>= 1.0.0) and legacy (0.28.x) clients.
    
    Args:
        system_prompt: System message content.
        user_prompt: User message content.
        model: Model name (default: from settings).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature.
    
    Returns:
        Assistant's response content.
    
    Raises:
        RuntimeError: If OpenAI call fails after all retries.
    """
    _initialize_client()
    
    settings = get_settings()
    if model is None:
        model = settings.openai_model_mini
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # Try modern client first
    if _openai_client and hasattr(_openai_client, 'chat'):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = _openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e:
                LOGGER.warning("OpenAI modern client attempt %d failed: %s", attempt, e)
                if attempt == MAX_RETRIES or not _is_transient_error(e):
                    raise
                _sleep_with_backoff(attempt)
    
    # Fallback to legacy client
    try:
        import openai
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                c = response.choices[0]
                if hasattr(c, "message"):
                    return c.message["content"] if isinstance(c.message, dict) else c.message.content
                if hasattr(c, "text"):
                    return c.text
                return response["choices"][0].get("message", {}).get("content", "")
            except Exception as e:
                LOGGER.warning("OpenAI legacy client attempt %d failed: %s", attempt, e)
                if attempt == MAX_RETRIES or not _is_transient_error(e):
                    raise
                _sleep_with_backoff(attempt)
    except ImportError:
        pass
    
    raise RuntimeError("OpenAI call failed: no working client available or all retries exhausted")


def call_openai_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.7
) -> Dict[str, Any]:
    """
    Call OpenAI and parse JSON response.
    
    Args:
        system_prompt: System message content.
        user_prompt: User message content.
        model: Model name (default: from settings).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature.
    
    Returns:
        Parsed JSON dictionary.
    
    Raises:
        ValueError: If response is not valid JSON.
        RuntimeError: If OpenAI call fails.
    """
    import json
    import re
    
    response = call_openai_chat(
        system_prompt=system_prompt + "\n\nRespond ONLY with valid JSON, no markdown.",
        user_prompt=user_prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    # Clean response (remove markdown if present)
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Remove markdown code blocks
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}\nResponse: {response[:200]}")
