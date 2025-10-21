import io
import json
import types
import inspect
import jsonpickle

from collections.abc import Mapping, Sequence
from jsonpickle.handlers import BaseHandler

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

PICKLER = jsonpickle.Pickler(
    unpicklable=False,
    make_refs=False,
    max_depth=1,
    warn=True,
    fail_safe=lambda obj: f'<non-serializable: {type(obj).__name__}>'
)

EXT_PICKLER = jsonpickle.Pickler(
    warn=True,
    fail_safe=lambda obj: f'<non-serializable: {type(obj).__name__}>'
)

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

def serialize(x):
    if isinstance(x, PRIMITIVES):
        return x
    
    if isinstance(x, tuple(REGISTERED_EXT_TYPES)):
        return EXT_PICKLER.flatten(x)
    
    if isinstance(x, Mapping):
        out = {}
        for k, v in x.items():
            out[str(k)] = serialize(v)
        return out
    
    if isinstance(x, (list, tuple, set, frozenset)):
        out = []
        for v in list(x):
            out.append(serialize(v))
        return out if not isinstance(x, tuple) else tuple(out)
    
    if any([
        inspect.isfunction(x), inspect.ismethod(x), inspect.isclass(x),
        inspect.isframe(x), inspect.iscode(x), inspect.istraceback(x),
        isinstance(x, (types.GeneratorType, types.ModuleType, io.IOBase)),
        hasattr(x, '__iter__') and not isinstance(x, (str, bytes, bytearray, Mapping, Sequence)),
    ]):
        return f"<{type(x).__name__}>"

    return PICKLER.flatten(x)

def dump(x):
    return json.dumps(serialize(x))

def deserialize(x):
    return jsonpickle.decode(json.dumps(x))