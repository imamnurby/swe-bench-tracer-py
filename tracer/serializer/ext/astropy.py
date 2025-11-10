import inspect

from jsonpickle.handlers import BaseHandler, register

ASTROPY_REGISTRY = []

def canonical_class_name(obj):
    return "{}.{}".format(obj.__class__.__module__, obj.__class__.__qualname__)

def safe_hasattr(obj, attr):
    try:
        inspect.getattr_static(obj, attr)
        return True
    except AttributeError:
        return False

# Handlers adapted from Astropy's YAML serialization
# https://docs.astropy.org/en/latest/_modules/astropy/io/misc/yaml.html
class UnitHandler(BaseHandler):
    def flatten(self, obj, data):
        result = {"py/object": canonical_class_name(obj)}
        if safe_hasattr(obj, "to_string"):
            result["unit"] = obj.to_string()
        return result

    def restore(self, obj):
        return obj

class GeneralAstropyHandler(BaseHandler):
    def flatten(self, obj, data):
        result =  {"py/object": canonical_class_name(obj)}
        if safe_hasattr(obj, "info") and safe_hasattr(obj.info, "_represent_as_dict"):
            result.update(
                self.context.flatten(obj.info._represent_as_dict())
            )
        return result

    def restore(self, obj):
        return obj

class ColumnHandler(BaseHandler):
    def flatten(self, obj, data):
        result =  {"py/object": canonical_class_name(obj)}
        try:
            result.update(
                self.context.flatten({
                    "data": obj.data,
                    "name": obj.name,
                    "unit": obj.unit,
                    "format": obj.format, 
                })
            )
        except AttributeError:
            pass
        return result

    def restore(self, obj):
        return obj

class TableHandler(BaseHandler):
    def flatten(self, obj, data):
        result =  {"py/object": canonical_class_name(obj)}
        try:
            result.update(
                self.context.flatten({
                    "columns": obj.columns,
                    "masked": obj.masked,
                })
            )
        except AttributeError:
            pass
        return result

    def restore(self, obj):
        return obj

def try_import_astropy(mod_name: str, class_names: list[str], handler: BaseHandler, base=False):
    for class_name in class_names:
        try:
            mod = __import__(mod_name, fromlist=[class_name])
            if hasattr(mod, class_name):
                cls = getattr(mod, class_name)
                ASTROPY_REGISTRY.append((cls, handler, base))
        except ImportError:
            pass

try_import_astropy(
    "astropy.units", 
    ["UnitBase", "FunctionUnitBase", "StructuredUnit"],
    UnitHandler,
    base=True,
)
try_import_astropy(
    "astropy.units", 
    ["Quantity", "Magnitude", "Dex", "Decibel"],
    GeneralAstropyHandler,
    base=True,
)
try_import_astropy(
    "astropy.coordinates",
    ["Angle", "Latitude", "Longitude"],
    GeneralAstropyHandler,
    base=True,
)
try_import_astropy(
    "astropy.coordinates",
    ["SkyCoord"],
    GeneralAstropyHandler,
)
try_import_astropy(
    "astropy.coordinates.earth",
    ["EarthLocation"],
    GeneralAstropyHandler,
    base=True,
)
try_import_astropy(
    "astropy.time",
    ["Time", "TimeDelta"],
    GeneralAstropyHandler,
)
try_import_astropy(
    "astropy.table",
    ["ColumnInfo"],
    GeneralAstropyHandler,
    base=True,
)
try_import_astropy(
    "astropy.table.column",
    ["BaseColumn"],
    ColumnHandler,
    base=True,
)
try_import_astropy(
    "astropy.table",
    ["Table"],
    TableHandler,
    base=True,
)

def register_handlers():
    for cls, handler, base in ASTROPY_REGISTRY:
        register(cls, handler, base=base)
    return [cls for cls, _, _ in ASTROPY_REGISTRY]
