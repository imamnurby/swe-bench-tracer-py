import sys
import inspect
import threading

from types import CodeType, FrameType

def get_members_static(obj, predicate=None):
    out = []
    for name in dir(obj):
        try:
            attr = inspect.getattr_static(obj, name)
        except Exception:
            continue
        if predicate is None or predicate(attr):
            out.append((name, attr))
    return out

class ThreadSafeCache:
    def __init__(self, max_size):
        self._cache = {}
        self._lock = threading.Lock()
        self._max_size = max_size
    
    def get_or_set(self, key, factory):
        with self._lock:
            if key not in self._cache:
                if len(self._cache) >= self._max_size:
                    self._cache.clear()
                self._cache[key] = factory()
            return self._cache[key]

QUALNAME_CACHE = ThreadSafeCache(max_size=131072)

def get_func_qualname(frame: FrameType) -> str:
    if sys.version_info >= (3, 11):
        return frame.f_code.co_qualname
    key = (frame.f_code.co_filename, frame.f_code.co_name, frame.f_code.co_firstlineno)
    return QUALNAME_CACHE.get_or_set(key, lambda: _get_func_qualname(frame))

def _get_func_qualname(frame: FrameType) -> str:
    for val in frame.f_globals.values():
        # function is global in the module
        if inspect.isfunction(val) and val.__code__ is frame.f_code:
            return val.__qualname__
        # function is a method in a class in the module
        if inspect.isclass(val):
            # check all methods of the class
            try:
                from types import GenericAlias
                if isinstance(val, GenericAlias):
                    val = val.__origin__
            except ImportError:
                pass
            for _, method in get_members_static(val, predicate=lambda x: inspect.isfunction(x) or inspect.ismethod(x)):
                if hasattr(method, '__code__') and method.__code__ is frame.f_code:
                    return method.__qualname__
    # function is a nested function; we only support one level of nesting for now
    for val in frame.f_globals.values():
        if inspect.isfunction(val):
            for const in val.__code__.co_consts:
                if isinstance(const, CodeType) and const is frame.f_code:
                    return "{}.<locals>.{}".format(val.__qualname__, frame.f_code.co_name)
    return frame.f_code.co_name
