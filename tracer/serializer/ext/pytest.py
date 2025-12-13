from jsonpickle.handlers import BaseHandler, register

PYTEST_REGISTRY = []

def canonical_class_name(obj):
    return "{}.{}".format(obj.__class__.__module__, obj.__class__.__qualname__)

class PytestPluginManagerHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"py/object": canonical_class_name(obj)}
    
    def restore(self, obj):
        return obj

class ConfigHandler(BaseHandler):
    ...

class NodeHandler(BaseHandler):
    def flatten(self, obj, data):
        result = {"py/object": canonical_class_name(obj)}
        try:
            result.update({
                "name": obj.name,
                "nodeid": obj._nodeid,
                "path": obj.path,
            })
        except Exception:
            pass
        return result
    
    def restore(self, obj):
        return obj

def try_import_pytest(mod_name, class_names, handler, base=False):
    for class_name in class_names:
        try:
            mod = __import__(mod_name, fromlist=[class_name])
            if hasattr(mod, class_name):
                cls = getattr(mod, class_name)
                PYTEST_REGISTRY.append((cls, handler, base))
        except ImportError:
            pass

def register_handlers():
    for cls, handler, base in PYTEST_REGISTRY:
        register(cls, handler, base=base)
    return [cls for cls, _, _ in PYTEST_REGISTRY]
