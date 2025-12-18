from functools import partial

from jsonpickle.handlers import BaseHandler
from tracer.serializer.ext.common import (
    PlainHandler,
    try_import,
    register_registry_handlers,
    canonical_class_name,
)

# try_import_xarray = partial(try_import, registry='xarray')
# register_handlers = partial(register_registry_handlers, registry='xarray')

