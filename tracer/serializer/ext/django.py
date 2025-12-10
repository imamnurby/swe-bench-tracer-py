from jsonpickle.handlers import BaseHandler, register

DJANGO_REGISTRY = []

def canonical_class_name(obj):
    return "{}.{}".format(obj.__class__.__module__, obj.__class__.__qualname__)

class PaginatorHandler(BaseHandler):
    def flatten(self, obj, data):
        result = {"py/object": canonical_class_name(obj)}
        try:
            result.update({
                "per_page": obj.per_page,
                "orphans": obj.orphans,
                "allow_empty_first_page": obj.allow_empty_first_page,
                "__dir__": dir(obj),
            })
        except Exception:
            pass
        return result
    
    def restore(self, obj):
        return obj

class DjangoSimpleTestCaseHandler(BaseHandler):
    def flatten(self, obj, data):
        result = {"py/object": canonical_class_name(obj)}
        try:
            result.update({
                "client": self.context.flatten(obj.client),
            })
        except Exception:
            pass
        return result
    
    def restore(self, obj):
        return obj

class ImmutableListHandler(BaseHandler):
    def flatten(self, obj, data):
        try:
            result = self.context.flatten(list(obj))
        except Exception:
            result = {"py/object": canonical_class_name(obj)}
        return result
    
    def restore(self, obj):
        return obj

# class ModelHandler(BaseHandler):
#     def flatten(self, obj, data):
#         result = {"py/object": canonical_class_name(obj)}
#         try:
#             from django.core.serializers import serialize as django_serialize
#             result.update({
#                 "serialized": django_serialize('json', obj.objects.all())
#             })
#         except Exception:
#             pass
#         return result
    
#     def restore(self, obj):
#         return obj

class DatabaseWrapperHandler(BaseHandler):
    def flatten(self, obj, data):
        return {"py/object": canonical_class_name(obj)}
    
    def restore(self, obj):
        return obj

def try_import_django(mod_name: str, class_names: list, handler: BaseHandler, base=False):
    for class_name in class_names:
        try:
            mod = __import__(mod_name, fromlist=[class_name])
            if hasattr(mod, class_name):
                cls = getattr(mod, class_name)
                DJANGO_REGISTRY.append((cls, handler, base))
        except ImportError:
            pass

try_import_django(
    "django.core.paginator",
    ["Paginator"],
    PaginatorHandler,
    base=True,
)
try_import_django(
    "django.test",
    ["SimpleTestCase"],
    DjangoSimpleTestCaseHandler,
    base=True,
)
try_import_django(
    "django.utils.datastructures",
    ["ImmutableList"],
    ImmutableListHandler,
)
# try_import_django(
#     "django.db.models.base",
#     ["Model"],
#     ModelHandler,
#     base=True,
# )
try_import_django(
    "django.db.backends.base.base",
    ["BaseDatabaseWrapper"],
    DatabaseWrapperHandler,
    base=True,
)
try_import_django(
    "django.db.backends.sqlite3.base",
    ["DatabaseWrapper"],
    DatabaseWrapperHandler,
)

def register_handlers():
    for cls, handler, base in DJANGO_REGISTRY:
        register(cls, handler, base=base)
    return [cls for cls, _, _ in DJANGO_REGISTRY]