from functools import partial

from jsonpickle.handlers import BaseHandler
from tracer.serializer.ext.common import (
    PlainHandler,
    try_import,
    register_registry_handlers,
    canonical_class_name,
)

try_import_sphinx = partial(try_import, registry='sphinx')
register_handlers = partial(register_registry_handlers, registry='sphinx')

class MessageHandler(BaseHandler):
    def flatten(self, obj, data):
        results = {"py/object": canonical_class_name(obj)}
        try:
            results.update({
                "text": obj.text,
                "locations": self.context.flatten(obj.locations),
            })
        except Exception:
            pass
        return results

    def restore(self, obj):
        return obj

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
try_import_sphinx(
    "sphinx.parsers",
    ["Parser"],
    PlainHandler,
    base=True,
)
try_import_sphinx(
    "sphinx.builders",
    ["Builder"],
    PlainHandler,
)
try_import_sphinx(
    "sphinx.builders.gettext",
    ["Message"],
    MessageHandler,
)
try_import_sphinx(
    "docutils.parsers.rst.states",
    ["RSTStateMachine", "RSTState", "Inliner", "Body"],
    PlainHandler,
    base=True,
)