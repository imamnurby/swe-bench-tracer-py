from functools import partial

from jsonpickle.handlers import BaseHandler
from tracer.serializer.ext.common import (
    try_import,
    register_registry_handlers,
    canonical_class_name,
)

try_import_xarray = partial(try_import, registry='xarray')
register_handlers = partial(register_registry_handlers, registry='xarray')

class VariableHandler(BaseHandler):
    def flatten(self, obj, data):
        results = {"py/object": canonical_class_name(obj)}
        try:
            results.update(self.context.flatten(obj.to_dict()))
        except Exception:
            pass
        return results

    def restore(self, obj):
        return obj

class DataArrayHandler(BaseHandler):
    def flatten(self, obj, data):
        results = {"py/object": canonical_class_name(obj)}
        try:
            results.update(self.context.flatten({
                "_variable": obj._variable,
                "_coords": obj._coords,
                "_name": obj._name,
                "_indexes": obj._indexes,
            }))
        except Exception:
            pass
        return results

    def restore(self, obj):
        return obj

try_import_xarray(
    "xarray.core.variable",
    ["Variable"],
    VariableHandler,
)
try_import_xarray(
    "xarray.core.dataarray",
    ["DataArray"],
    DataArrayHandler,
)