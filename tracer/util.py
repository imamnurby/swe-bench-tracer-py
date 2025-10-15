import sys
import inspect
import jsonpickle
import orjson as json

from jsonpickle.ext import numpy as jsonpickle_numpy
from jsonpickle.ext import pandas as jsonpickle_pandas

from types import CodeType, FrameType, GenericAlias

jsonpickle_numpy.register_handlers()
jsonpickle_pandas.register_handlers()

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
            return json.loads(jsonpickle.encode(obj))
        except Exception:
            return f'<non-serializable: {type(obj).__name__}>'
    try:
        json.dumps(value)
        return value
    except Exception:
        return jsonpickle_fallback(value)

def safe_dump(obj):
    return json.dumps(obj, default=sanitize_for_json).decode()

def safe_serialize(obj):
    return json.loads(json.dumps(obj, default=sanitize_for_json))
