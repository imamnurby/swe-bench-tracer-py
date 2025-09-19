import sys
import inspect
import warnings

from types import CodeType, FrameType

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
            for _, method in inspect.getmembers(val, predicate=lambda x: inspect.isfunction(x) or inspect.ismethod(x)):
                if method.__code__ is frame.f_code:
                    return method.__qualname__
    # function is a nested function; we only support one level of nesting for now
    for val in frame.f_globals.values():
        if inspect.isfunction(val):
            for const in val.__code__.co_consts:
                if isinstance(const, CodeType) and const is frame.f_code:
                    return f"{val.__qualname__}.<locals>.{frame.f_code.co_name}"
    warnings.warn(f"Cannot determine qualname, fallback to co_name: {frame.f_code.co_name}")
    return frame.f_code.co_name