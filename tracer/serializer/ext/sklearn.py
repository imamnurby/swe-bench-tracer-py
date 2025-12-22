from functools import partial
from tracer.serializer.ext.common import (
    PlainHandler,
    try_import,
    register_registry_handlers,
)

try_import_sklearn = partial(try_import, registry='sklearn')
register_handlers = partial(register_registry_handlers, registry='sklearn')

try_import_sklearn(
    "sklearn.externals.joblib.memory",
    ["Memory"],
    PlainHandler,
)
