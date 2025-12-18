from functools import partial

from tracer.serializer.ext.common import (
    PlainHandler,
    try_import,
    register_registry_handlers,
)

try_import_sphinx = partial(try_import, registry='sphinx')
register_handlers = partial(register_registry_handlers, registry='sphinx')

try_import_sphinx(
    "sphinx.testing.util",
    ["SphinxTestApp"],
    PlainHandler,
    base=True,
)
try_import_sphinx(
    "sphinx.io",
    ["SphinxBaseReader"],
    PlainHandler,
    base=True,
)