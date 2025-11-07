import os
import pkgutil
import importlib

__all__ = ['register_handlers']

def register_handlers():
    registered_types = []
    dir = os.path.abspath(os.path.dirname(__file__))
    for _, modname, _ in pkgutil.iter_modules([dir]):
        module = importlib.import_module(f'tracer.serializer.ext.{modname}')
        if hasattr(module, 'register_handlers'):
            registered_types.extend(module.register_handlers() or [])
    return registered_types
