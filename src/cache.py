import diskcache
from pathlib import Path

cache_dir = Path("cache")
cache_dir.mkdir(exist_ok=True)
cache = diskcache.Cache(str(cache_dir))

def get_cached_response(query: str, patient_id: int) -> str | None:
    key = f"{patient_id}:{query.lower().strip()}"
    return cache.get(key)

def set_cached_response(query: str, patient_id: int, response: str):
    key = f"{patient_id}:{query.lower().strip()}"
    cache.set(key, response, expire=3600)
