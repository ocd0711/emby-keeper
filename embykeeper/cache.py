import json
from typing import Any, List

from loguru import logger

from .utils import CachedFuncProxy
from .config import config

class Cache:
    def __init__(self):
        self._mongo_client = None
        if hasattr(config, 'mongodb') and config.mongodb:
            try:
                from pymongo import MongoClient
                
                self._mongo_client = MongoClient(config.mongodb)
                self._db = self._mongo_client.embykeeper
                self._collection = self._db.cache
            except ImportError:
                logger.warning("没有安装 pymongo 包, 将使用 JSON 存储缓存.")
                self._setup_json_cache()
        else:
            self._setup_json_cache()
    
    def _setup_json_cache(self):
        self._cache_file = config.basedir / "cache.json"
        self._data = {}
        if self._cache_file.exists():
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except json.JSONDecodeError:
                logger.warning("缓存文件损坏, 将使用全新缓存.")

    def get(self, key: str, default: Any = None) -> Any:
        if self._mongo_client:
            result = self._collection.find_one({"_id": key})
            return result["value"] if result else default
        else:
            value = self._data
            try:
                for part in key.split('.'):
                    value = value.get(part, {})
                return default if value == {} else value
            except (AttributeError, TypeError):
                return default

    def set(self, key: str, value: Any) -> None:
        if self._mongo_client:
            self._collection.update_one(
                {"_id": key},
                {"$set": {"value": value}},
                upsert=True
            )
        else:
            parts = key.split('.')
            current = self._data
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = value
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False)

    def delete(self, key: str) -> None:
        if self._mongo_client:
            self._collection.delete_one({"_id": key})
        else:
            parts = key.split('.')
            current = self._data
            path = []
            for part in parts[:-1]:
                if part not in current:
                    return
                current = current[part]
                path.append((part, current))
            
            if parts[-1] in current:
                del current[parts[-1]]
                
                for part, parent in reversed(path):
                    if not parent[part]:
                        del parent[part]
                    else:
                        break
                        
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

    def find_by_prefix(self, prefix: str) -> List[str]:
        if self._mongo_client:
            return [doc["_id"] for doc in self._collection.find(
                {"_id": {"$regex": f"^{prefix}"}}, 
                {"_id": 1}
            )]
        else:
            def get_keys_with_prefix(d, current_path="", keys=None):
                if keys is None:
                    keys = []
                for k, v in d.items():
                    path = f"{current_path}.{k}" if current_path else k
                    if isinstance(v, dict):
                        get_keys_with_prefix(v, path, keys)
                    else:
                        if path.startswith(prefix):
                            keys.append(path)
                return keys
            
            return get_keys_with_prefix(self._data)

cache: Cache = CachedFuncProxy(lambda: Cache())