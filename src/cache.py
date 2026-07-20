import diskcache
from pathlib import Path

cache_dir = Path("cache")
cache_dir.mkdir(exist_ok=True)
cache = diskcache.Cache(str(cache_dir))

# NOTE: cached responses can contain PHI (e.g. a patient's own lab results
# echoed back to them). They're written to plain, unencrypted files under
# cache/ (excluded from git, but still readable by anything with disk
# access). Keep the TTL short and restrict filesystem permissions on this
# folder in production; don't raise this value without also addressing
# at-rest encryption for the whole app.
CACHE_TTL_SECONDS = 600  # 10 minutes (was 1 hour)

def get_cached_response(query: str, patient_id: int) -> str | None:
    key = f"{patient_id}:{query.lower().strip()}"
    return cache.get(key)

def set_cached_response(query: str, patient_id: int, response: str):
    key = f"{patient_id}:{query.lower().strip()}"
    cache.set(key, response, expire=CACHE_TTL_SECONDS)
