import io
import json
import types
import inspect
import jsonpickle

from decimal import Decimal
from collections.abc import Mapping, Sequence, Set
from jsonpickle.handlers import BaseHandler

def registry_get_monkey_patch(self):
    '''
    - Base handler is registered for type A
    - An instance of type B (subclass of A) is requested
    - Only return the base handler if A and B are defined in the same module
    '''
    def is_same_module(cls_or_name: type, cls: type):
        return cls_or_name.__module__ == cls.__module__
    
    def get(cls_or_name, default=None):
        handler = self._handlers.get(cls_or_name)
        # attempt to find a base class
        if handler is None and jsonpickle.util.is_type(cls_or_name):
            for cls, base_handler in self._base_handlers.items():
                if issubclass(cls_or_name, cls) and is_same_module(cls_or_name, cls):
                    return base_handler
        return default if handler is None else handler
    return get

jsonpickle.handlers.get = registry_get_monkey_patch(jsonpickle.handlers.registry)

REGISTERED_EXT_TYPES = []

try:
    import numpy as np
    from jsonpickle.ext import numpy as jsonpickle_numpy
    jsonpickle_numpy.register_handlers()
    REGISTERED_EXT_TYPES.extend([
        np.ndarray, np.dtype, np.generic, np.dtype(np.void).__class__,
        np.dtype(np.float32).__class__, np.dtype(np.int32).__class__,
        np.dtype(np.datetime64).__class__, np.datetime64,
    ])
except ImportError:
    pass

try:
    import pandas as pd
    from jsonpickle.ext import pandas as jsonpickle_pandas
    jsonpickle_pandas.register_handlers()
    REGISTERED_EXT_TYPES.extend([
        pd.DataFrame, pd.Series, pd.Index, pd.PeriodIndex,
        pd.MultiIndex, pd.Timestamp, pd.Period, pd.Interval,
    ])
except ImportError:
    pass

PRIMITIVES = (type(None), bool, int, float, str)
PICKLER = jsonpickle.Pickler(warn=True)
UNPICKLER = jsonpickle.Unpickler()

@jsonpickle.handlers.register(type(iter([])))
class IteratorHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"__iterator__": type(obj).__name__}

@jsonpickle.handlers.register(types.GeneratorType)
class GeneratorHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"__generator__": getattr(obj, 'gi_code').co_name if hasattr(obj, 'gi_code') else type(obj).__name__}

@jsonpickle.handlers.register(io.IOBase)
class FileHandler(BaseHandler):
    def flatten(self, obj, data):
        try:
            name = obj.name
        except Exception:
            name = None
        return {"__file__": True, "name": name, "closed": obj.closed}

def non_serializable(obj):
    return "<{}>".format(type(obj).__name__)

def serialize(x):
    if isinstance(x, PRIMITIVES):
        return x
    
    if isinstance(x, Decimal):
        return float(x)
    
    if isinstance(x, tuple(REGISTERED_EXT_TYPES)):
        try:
            return PICKLER.flatten(x)
        except AttributeError:
            return non_serializable(x)
    
    if isinstance(x, Mapping):
        out = {}
        for k, v in x.items():
            out[str(k)] = serialize(v)
        return out
    
    if isinstance(x, (Sequence, Set)):
        try:
            out = []
            for v in list(x):
                out.append(serialize(v))
            return out if not isinstance(x, tuple) else tuple(out)
        except AttributeError:
            return non_serializable(x)
    
    if any([
        inspect.isfunction(x), inspect.ismethod(x), inspect.isclass(x),
        inspect.isframe(x), inspect.iscode(x), inspect.istraceback(x),
        isinstance(x, (types.GeneratorType, types.ModuleType, io.IOBase)),
        hasattr(x, '__iter__') and not isinstance(x, (str, bytes, bytearray, Mapping, Sequence)),
    ]):
        return non_serializable(x)
    
    try:
        return PICKLER.flatten(x)
    except Exception:
        return non_serializable(x)

def dump(x):
    return json.dumps(serialize(x))

def deserialize(x):
    try:
        return UNPICKLER.restore(x)
    except Exception:
        return x