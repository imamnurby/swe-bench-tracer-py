from jsonpickle.handlers import BaseHandler, register

SPHINX_REGISTRY = []

def canonical_class_name(obj):
    return "{}.{}".format(obj.__class__.__module__, obj.__class__.__qualname__)

class SphinxTestAppHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"py/object": canonical_class_name(obj)}
    
    def restore(self, obj):
        return obj

def try_import_sphinx(mod_name, class_names, handler, base=False):
    for class_name in class_names:
        try:
            mod = __import__(mod_name, fromlist=[class_name])
            if hasattr(mod, class_name):
                cls = getattr(mod, class_name)
                SPHINX_REGISTRY.append((cls, handler, base))
        except ImportError:
            pass
        except Exception as e:
            print("Error when importing {}.{}: {} - {}".format(mod_name, class_name, type(e).__name__, e))

try_import_sphinx(
    "sphinx.testing.util",
    ["SphinxTestApp"],
    SphinxTestAppHandler,
    base=True,
)

def register_handlers():
    for cls, handler, base in SPHINX_REGISTRY:
        register(cls, handler, base=base)
    return [cls for cls, _, _ in SPHINX_REGISTRY]