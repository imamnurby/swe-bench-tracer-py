import io
import sys
import json
import inspect
import jsonpickle

from functools import wraps
from itertools import count
from collections.abc import Mapping, Sequence, Set
from tracer.serializer.ext import register_handlers

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

REGISTERED_EXT_TYPES = register_handlers()
PRIMITIVES = (type(None), bool, int, float, str)
PICKLER = jsonpickle.Pickler(warn=True)
UNPICKLER = jsonpickle.Unpickler()

def pickler_flatten_function_monkey_patch(self):
    def _flatten_function(obj):
        if self.unpicklable:
            name = jsonpickle.util.importable_name(obj)
            data = {jsonpickle.tags.FUNCTION: name}
            if not name.startswith('builtins.'):
                data['__doc__'] = obj.__doc__
        else:
            data = None
        return data
    return _flatten_function

PICKLER._flatten_function = pickler_flatten_function_monkey_patch(PICKLER)

def unpickler_restore_function_monkey_patch(self):
    def _restore_function(obj):
        return obj
    return _restore_function

UNPICKLER._restore_function = unpickler_restore_function_monkey_patch(UNPICKLER)

def safe_hasattr(obj, attr):
    try:
        inspect.getattr_static(obj, attr)
        return True
    except AttributeError:
        return False

def non_serializable(obj, exc=None):
    if exc:
        msg = str(exc)
        if isinstance(exc, UserWarning) and '<lambda>' not in msg:
            print(msg, file=sys.stderr, flush=True)
        elif not isinstance(exc, RecursionError):
            print('Object of type "{}" is non-serializable due to {}: {}'.format(type(obj).__name__, type(exc).__name__, msg), file=sys.stderr, flush=True)
            print('--- object repr ---', file=sys.stderr, flush=True)
            print(obj, file=sys.stderr, flush=True)
    return "<{}>".format(type(obj).__name__)

def get_stackdepth(size=2):
    if sys._getframe().f_back.f_back is None:
        return 1
    frame = sys._getframe(size)
    for size in count(size):
        frame = frame.f_back
        if not frame:
            return size

def exception_guard(func):
    @wraps(func)
    def wrapper(x):
        recursion_limit = sys.getrecursionlimit()
        new_limit = min(recursion_limit, get_stackdepth() + 200)
        try:
            if new_limit < recursion_limit:
                sys.setrecursionlimit(new_limit)
            return func(x)
        except Exception as e:
            return non_serializable(x, e)
        finally:
            if sys.getrecursionlimit() != recursion_limit:
                sys.setrecursionlimit(recursion_limit)
    return wrapper

@exception_guard
def serialize(x):
    if isinstance(x, PRIMITIVES):
        return x
    
    if isinstance(x, tuple(REGISTERED_EXT_TYPES)):
        return PICKLER.flatten(x)
    
    if isinstance(x, Mapping):
        out = {}
        for k, v in x.items():
            out[str(k)] = serialize(v)
        return out
    
    if isinstance(x, (Sequence, Set)):
        out = []
        for v in list(x):
            out.append(serialize(v))
        return out if not isinstance(x, tuple) else tuple(out)

    if any([
        inspect.isframe(x), inspect.iscode(x), inspect.istraceback(x),
        safe_hasattr(x, '__iter__') and not isinstance(x, (bytes, bytearray, io.IOBase)),
    ]):
        return non_serializable(x)
    
    return PICKLER.flatten(x)

def dump(x):
    return json.dumps(serialize(x))

def deserialize(x):
    try:
        return UNPICKLER.restore(x)
    except Exception:
        return x