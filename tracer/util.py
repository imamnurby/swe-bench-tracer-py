import sys
import inspect
import jsonpickle
import json

from types import CodeType, FrameType, GenericAlias

try:
    from jsonpickle.ext import numpy as jsonpickle_numpy
    jsonpickle_numpy.register_handlers()
except ImportError:
    pass

try:
    from jsonpickle.ext import pandas as jsonpickle_pandas
    jsonpickle_pandas.register_handlers()
except ImportError:
    pass

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
    return frame.f_code.co_name

def sanitize_for_json(value):
    def jsonpickle_fallback(obj):
        try:
            return json.loads(
                jsonpickle.encode(obj, unpicklable=False, make_refs=False)
            )
        except Exception:
            return f'<non-serializable: {type(obj).__name__}>'
    try:
        json.dumps(value)
        return value
    except Exception:
        return jsonpickle_fallback(value)

def sanitize_for_dict(value):
    if isinstance(value, list):
        return [sanitize_for_dict(v) for v in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_dict(v) for v in value)
    if not isinstance(value, dict):
        return value
    result = {}
    for k, v in value.items():
        if not isinstance(k, (str, int, float, bool, type(None))):
            k = str(k)
        result[k] = sanitize_for_dict(v)
    return result

def safe_dump(obj):
    return json.dumps(obj, default=sanitize_for_json)

def safe_serialize(obj):
    obj = sanitize_for_dict(obj)
    return json.loads(json.dumps(obj, default=sanitize_for_json))

def safe_deserialize(obj):
    return jsonpickle.decode(json.dumps(obj))
