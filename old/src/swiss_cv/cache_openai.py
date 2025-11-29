import os, json, hashlib, functools, time
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cache', 'openai')
os.makedirs(CACHE_DIR, exist_ok=True)

def _key_for(prompt: str):
    h = hashlib.sha256()
    h.update(prompt.encode('utf-8'))
    return h.hexdigest()

def cache_response(ttl_seconds=86400):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(prompt, *args, **kwargs):
            key = _key_for(prompt)
            path = os.path.join(CACHE_DIR, key + '.json')
            try:
                if os.path.exists(path):
                    stat = os.stat(path)
                    if (time.time() - stat.st_mtime) < ttl_seconds:
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f).get('result')
            except Exception:
                pass
            res = func(prompt, *args, **kwargs)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump({'result': res, 'ts': time.time()}, f, ensure_ascii=False)
            except Exception:
                pass
            return res
        return wrapper
    return decorator


