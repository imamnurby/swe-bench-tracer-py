from jsonpickle.handlers import BaseHandler, register

def canonical_class_name(obj):
    return "{}.{}".format(obj.__class__.__module__, obj.__class__.__qualname__)

NUMPY_EXT_REGISTRY = []

class MaskedArrayHandler(BaseHandler):
    def flatten(self, obj, data):
        result = {"py/object": canonical_class_name(obj)}
        try:
            result.update({
                "data": obj.data.tolist(),
                "mask": obj.mask.tolist(),
                "fill_value": obj.fill_value.tolist(),
                "dtype": self.context.flatten(obj.dtype),
            })
        except Exception:
            pass
        return result
    
    def restore(self, obj):
        try:
            from numpy.ma import MaskedArray
            return MaskedArray(
                data=obj['data'],
                mask=obj['mask'],
                fill_value=obj['fill_value'],
                dtype=self.context.restore(obj['dtype'], reset=False),
            )
        except Exception:
            return obj

class NumpyBoolHandler(BaseHandler):
    def flatten(self, obj, data):
        return bool(obj)
    
    def restore(self, obj):
        return obj

def try_import_numpy(mod_name, class_names, handler, base=False):
    for class_name in class_names:
        try:
            mod = __import__(mod_name, fromlist=[class_name])
            if hasattr(mod, class_name):
                cls = getattr(mod, class_name)
                NUMPY_EXT_REGISTRY.append((cls, handler, base))
        except ImportError:
            pass
        except Exception as e:
            print("Error when importing {}.{}: {} - {}".format(mod_name, class_name, type(e).__name__, e))

try_import_numpy(
    "numpy.ma",
    ["MaskedArray"],
    MaskedArrayHandler,
)
try_import_numpy(
    "numpy",
    ["bool_"],
    NumpyBoolHandler,
)

def register_handlers():
    for cls, handler, base in NUMPY_EXT_REGISTRY:
        register(cls, handler, base=base)
    return [cls for cls, _, _ in NUMPY_EXT_REGISTRY]
