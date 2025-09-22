import re
import sys
import pickle
import inspect
import warnings

from types import CodeType, FrameType, GenericAlias
from collections.abc import Mapping

def get_func_qualname(frame: FrameType) -> str:
    if sys.version_info >= (3, 11):
        return frame.f_code.co_qualname
    for val in frame.f_globals.values():
        # function is global in the module
        if inspect.isfunction(val) and val.__code__ is frame.f_code:
            return val.__qualname__
        # function is a method in a class in the module
        if inspect.isclass(val):
            # check all methods of the class
            if isinstance(val, GenericAlias):
                val = val.__origin__
            for _, method in inspect.getmembers(val, predicate=lambda x: inspect.isfunction(x) or inspect.ismethod(x)):
                if hasattr(method, '__code__') and method.__code__ is frame.f_code:
                    return method.__qualname__
    # function is a nested function; we only support one level of nesting for now
    for val in frame.f_globals.values():
        if inspect.isfunction(val):
            for const in val.__code__.co_consts:
                if isinstance(const, CodeType) and const is frame.f_code:
                    return f"{val.__qualname__}.<locals>.{frame.f_code.co_name}"
    warnings.warn(f"Cannot determine qualname, fallback to co_name: {frame.f_code.co_name}")
    return frame.f_code.co_name

def short_repr(obj):
    if obj is None:
        return "None"
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, (str, bytes)):
        s = str(obj)
        if len(s) > 10:
            return s[:7] + "..."
        return re.sub(r'\s+', '_', s)
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [short_repr(item) for item in list(obj)[:3]]
        return f"{type(obj).__name__}({','.join(items)}{'...' if len(obj) > 5 else ''})"
    return f"{type(obj).__name__}{hex(id(obj))}"

def call_signature(func, *args, **kwargs):
    sig = inspect.signature(func)
    bound = sig.bind_partial(*args, **kwargs)
    bound.apply_defaults()
    parts = []
    for name, value in bound.arguments.items():
        parts.append(f"{name}={short_repr(value)}")
    if len(parts) == 0:
        base = f"{func.__module__}.{func.__qualname__}"
    else:
        base = f"{func.__module__}.{func.__qualname__}__" + "__".join(parts)
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', base)
    return sanitized[:120]

def safe_pickle(obj):
    basic = (int, float, bool, str, bytes, type(None))
    if isinstance(obj, basic):
        return obj
    if isinstance(obj, Mapping):
        out = {}
        for k, v in obj.items():
            try:
                pickle.dumps(k)
                new_k = k
            except Exception:
                new_k = f'<non-picklable: {type(k).__name__}>'
            try:
                pickle.dumps(v)
                new_v = v
            except Exception:
                new_v = safe_pickle(v)
            out[new_k] = new_v
        return out
    if isinstance(obj, (list, tuple, set, frozenset)):
        seq_type = type(obj)
        new_seq = []
        for item in obj:
            try:
                pickle.dumps(item)
                new_seq.append(item)
            except Exception:
                new_seq.append(safe_pickle(item))
        return seq_type(new_seq)
    return f'<non-picklable: {type(obj).__name__}>'