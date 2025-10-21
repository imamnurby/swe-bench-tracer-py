import sys
import inspect

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
                    return f"{val.__qualname__}.<locals>.{frame.f_code.co_name}"
    return frame.f_code.co_name
