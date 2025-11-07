import io
import types
import socket
import decimal

from jsonpickle.handlers import BaseHandler, register

class IteratorHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"__iterator__": type(obj).__name__}

class GeneratorHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"__generator__": getattr(obj, 'gi_code').co_name if hasattr(obj, 'gi_code') else type(obj).__name__}

class FileHandler(BaseHandler):
    def flatten(self, obj: io.IOBase, data):
        try:
            name = obj.name
        except Exception:
            name = None
        return {"io.IOBase": {"name": name, "closed": obj.closed}}

class TextIOHandler(BaseHandler):
    def flatten(self, obj: io.TextIOWrapper, data):
        return {"io.TextIOWrapper": {"name": obj.name, "mode": obj.mode, "encoding": obj.encoding}}

class SocketHandler(BaseHandler):
    def flatten(self, obj: socket.socket, data):
        return {"socket.socket": {"fd": obj.fileno(), "family": obj.family, "type": obj.type, "proto": obj.proto}}

class DecimalHandler(BaseHandler):
    def flatten(self, obj: decimal.Decimal, data):
        return {"py/object": "decimal.Decimal", "value": str(obj)}
    
    def restore(self, obj):
        return decimal.Decimal(obj["value"])

class PropertyHandler(BaseHandler):
    def flatten(self, obj: property, data):
        fn = obj.fget
        if fn:
            fn.__doc__ = obj.__doc__
        return self.context.flatten(fn)

def register_handlers():
    register(type(iter([])), IteratorHandler)
    register(types.GeneratorType, GeneratorHandler)
    register(io.IOBase, FileHandler)
    register(io.TextIOWrapper, TextIOHandler)
    register(socket.socket, SocketHandler)
    register(decimal.Decimal, DecimalHandler)
    register(property, PropertyHandler)
    return [
        type(iter([])), types.GeneratorType, io.IOBase,
        io.TextIOWrapper, socket.socket, decimal.Decimal, property,
    ]
