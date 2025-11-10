import traceback
import numpy as np

from collections.abc import Sequence
from tracer.serializer import serialize, deserialize

def assert_equals(obj, expected):
    assert obj == expected, f"Provided: {obj}\nExpected: {expected}"

def test_func_types():
    def dummy_func(): ...
    class A: 
        def a(self): ...
    assert_equals(serialize(dummy_func), {'py/function': '__main__.test_func_types.<locals>.dummy_func', '__doc__': None})
    assert_equals(serialize(A.a), {'py/function': '__main__.test_func_types.<locals>.A.a', '__doc__': None})
    assert_equals(serialize(A().a), {'py/object': 'builtins.method'})
    assert_equals(serialize(len), {'py/function': 'builtins.len'})

def test_module_type():
    import math, sys
    assert_equals(serialize(math), {'py/mod': 'math/math'})
    assert_equals(serialize(sys.modules[__name__]), {'py/mod': '__main__/__main__'})

def test_dict_of_funcs_in_class():
    def dummy_func():
        pass
    class A:
        def __init__(self):
            self.data = {
                'key': dummy_func
            }
    
    data = A()
    serialized = serialize(data)
    assert_equals(serialized, {'py/object': '__main__.test_dict_of_funcs_in_class.<locals>.A', 'data': {'key': {'py/function': '__main__.test_dict_of_funcs_in_class.<locals>.dummy_func', '__doc__': None}}})

def test_normal_registered_type():
    arr = np.array([1, 2, 3])
    serialized = serialize(arr)
    assert_equals(serialized, {'py/object': 'numpy.ndarray', 'dtype': 'int64', 'values': [1, 2, 3]})
    deserialized = deserialize(serialized)
    assert_equals(arr.tolist(), deserialized.tolist())

def test_subclass_of_registered_type():
    class MyArray(np.ndarray):
        value = 42
    
    obj = np.array([1, 2, 3]).view(MyArray)
    serialized = serialize(obj)
    
    assert_equals(serialized, {'py/reduce': [{'py/function': 'numpy._core.multiarray._reconstruct', '__doc__': '_reconstruct(subtype, shape, dtype)\n\n    Construct an empty array. Used by Pickles.'}, {'py/tuple': [{'py/type': '__main__.test_subclass_of_registered_type.<locals>.MyArray'}, {'py/tuple': [0]}, {'py/b64': 'Yg=='}]}, {'py/tuple': [1, {'py/tuple': [3]}, {'py/reduce': [{'py/type': 'numpy.dtype'}, {'py/tuple': ['i8', False, True]}, {'py/tuple': [3, '<', None, None, None, -1, -1, 0]}]}, False, {'py/b64': 'AQAAAAAAAAACAAAAAAAAAAMAAAAAAAAA'}]}]})

def test_uninitialized_sequence():
    """
    Tests that the serializer can gracefully handle an uninitialized
    sequence-like object without raising an AttributeError.
    """
    class UninitializedSequence(Sequence):
        def __init__(self, data):
            self._data = list(data)
        def __len__(self):
            return len(self._data)
        def __getitem__(self, index):
            return self._data[index]

    uninitialized_obj = UninitializedSequence.__new__(UninitializedSequence)
    serialized = serialize(uninitialized_obj)    
    expected_output = "<UninitializedSequence>"
    assert_equals(serialized, expected_output)

def test_partially_initialized_numpy_array():
    """
    Tests that the serializer can handle a partially-initialized object
    that is a subclass of a registered type (like numpy.ndarray).
    This is from astropy-13033.
    """
    class UninitializedArray(np.ndarray):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self._name = "initialized"

        @property
        def name(self):
            return self._name
        
        # jsonpickle calls __reduce__ during serialization
        def __reduce__(self):
            return (self.__class__, (self.name,))

    base_array = np.array([1, 2, 3])

    # This creates an UninitializedArray instance.
    # `_name` is NOT set on this new instance.
    uninitialized_view = base_array.view(UninitializedArray)
    serialized = serialize(uninitialized_view)    
    assert_equals(serialized, "<UninitializedArray>")

def test_custom_handlers():
    import sys, socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.close()
    assert_equals(serialize(sock), {"py/object": "socket.socket", "fd": sock.fileno(), "family": sock.family, "type": sock.type, "proto": sock.proto})
    assert_equals(serialize(sys.stdout), {"py/object": "io.TextIOWrapper", "name": sys.stdout.name, "mode": sys.stdout.mode, "encoding": sys.stdout.encoding})

def test_decimal():
    from decimal import Decimal
    assert_equals(serialize(Decimal('10.5')), {'py/object': 'decimal.Decimal', 'value': '10.5'})
    assert_equals(serialize(Decimal('sNaN')), {'py/object': 'decimal.Decimal', 'value': 'sNaN'})
    assert_equals(serialize(Decimal('NaN')), {'py/object': 'decimal.Decimal', 'value': 'NaN'})
    assert_equals(serialize(Decimal('Inf')), {'py/object': 'decimal.Decimal', 'value': 'Infinity'})
    assert_equals(serialize(Decimal('-Inf')), {'py/object': 'decimal.Decimal', 'value': '-Infinity'})
    
def test_handlers_deserialize():
    from decimal import Decimal
    assert_equals(deserialize(serialize(Decimal('10.5'))), Decimal('10.5'))

def test_property_doc_handler():
    class Base:
        @property
        def bar(self):
            """base bar doc"""
            return 1

    class Sub(Base):
        @property
        def bar(self):
            return 2

    val = Sub.__dict__['bar']            # property with __doc__ = None
    super_method = getattr(Base, 'bar')  # property with a docstring

    assert_equals(serialize(val), {'py/function': '__main__.test_property_doc_handler.<locals>.Sub.bar', '__doc__': None})
    assert_equals(serialize(super_method), {'py/function': '__main__.test_property_doc_handler.<locals>.Base.bar', '__doc__': 'base bar doc'})

    val.__doc__ = super_method.__doc__

    assert_equals(serialize(val), {'py/function': '__main__.test_property_doc_handler.<locals>.Sub.bar', '__doc__': 'base bar doc'})

def test_custom_handlers2():
    import uuid
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    assert_equals(u1 != u2, True)
    assert_equals(serialize(u1) == serialize(u2), True)

    import datetime
    dt1 = datetime.datetime(2025, 1, 1, 12, 0, 0, 0, tzinfo=datetime.timezone.utc)
    d1 = datetime.date(2025, 1, 1)
    t1 = datetime.time(14, 30, 0, 0, tzinfo=datetime.timezone.utc)
    assert_equals(serialize(dt1), {'py/object': 'datetime.datetime', 'year': 2025, 'month': 1, 'day': 1, 'hour': 12, 'minute': 0, 'second': 0, 'microsecond': 0, 'tzinfo': {'py/reduce': [{'py/type': 'datetime.timezone'}, {'py/tuple': [{'py/reduce': [{'py/type': 'datetime.timedelta'}, {'py/tuple': [0, 0, 0]}]}]}]}, 'fold': 0})
    assert_equals(serialize(d1), {'py/object': 'datetime.date', 'year': 2025, 'month': 1, 'day': 1})
    assert_equals(serialize(t1), {'py/object': 'datetime.time', 'hour': 14, 'minute': 30, 'second': 0, 'microsecond': 0, 'tzinfo': {'py/reduce': [{'py/type': 'datetime.timezone'}, {'py/tuple': [{'py/reduce': [{'py/type': 'datetime.timedelta'}, {'py/tuple': [0, 0, 0]}]}]}]}})

def test_astropy_handler():
    try:
        from astropy import units as u
        from astropy.time import Time
        from astropy.units import Quantity
        from astropy.table import Table, Column
        from astropy.coordinates import EarthLocation
    except ImportError:
        print(f"test_astropy_handler: SKIPPED (astropy not installed)")
        return
    
    t = Time(2457389.0, format='mjd', location=EarthLocation(1000, 2000, 3000, unit=u.km))
    q = Quantity([1, 2, 3], unit=u.km)
    col = Column(data=[1 , 2, 3], name='a', unit=u.km)
    tab = Table([[1, 2, 3], [4, 5, 6]], names=('a', 'b'), units=(u.km, u.km))
    
    assert_equals(serialize(t), {'py/object': 'astropy.time.core.Time', 'jd1': 4857390.0, 'jd2': -0.5, 'format': 'mjd', 'scale': 'utc', 'precision': 3, 'in_subfmt': '*', 'out_subfmt': '*', 'location': {'py/object': 'astropy.coordinates.earth.EarthLocation', 'x': {'py/object': 'astropy.units.quantity.Quantity', 'value': {'py/object': 'numpy.float64', 'dtype': 'float64', 'value': 1000.0}, 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}}, 'y': {'py/object': 'astropy.units.quantity.Quantity', 'value': {'py/object': 'numpy.float64', 'dtype': 'float64', 'value': 2000.0}, 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}}, 'z': {'py/object': 'astropy.units.quantity.Quantity', 'value': {'py/object': 'numpy.float64', 'dtype': 'float64', 'value': 3000.0}, 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}}, 'ellipsoid': 'WGS84'}})
    assert_equals(serialize(q), {'py/object': 'astropy.units.quantity.Quantity', 'value': {'py/object': 'numpy.ndarray', 'base': {'py/object': 'numpy.ndarray', 'dtype': 'float64', 'values': [1.0, 2.0, 3.0]}, 'shape': (3,), 'dtype': 'float64', 'values': [1.0, 2.0, 3.0]}, 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}})
    assert_equals(serialize(col), {'py/object': 'astropy.table.column.Column', 'data': {'py/object': 'numpy.ndarray', 'base': {'py/object': 'numpy.ndarray', 'dtype': 'int64', 'values': [1, 2, 3]}, 'shape': (3,), 'dtype': 'int64', 'values': [1, 2, 3]}, 'name': 'a', 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}, 'format': None})
    assert_equals(serialize(tab), {'py/object': 'astropy.table.table.Table', 'columns': {'py/object': 'astropy.table.table.TableColumns', 'a': {'py/object': 'astropy.table.column.Column', 'data': {'py/object': 'numpy.ndarray', 'base': {'py/object': 'numpy.ndarray', 'dtype': 'int64', 'values': [1, 2, 3]}, 'shape': (3,), 'dtype': 'int64', 'values': [1, 2, 3]}, 'name': 'a', 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}, 'format': None}, 'b': {'py/object': 'astropy.table.column.Column', 'data': {'py/object': 'numpy.ndarray', 'base': {'py/object': 'numpy.ndarray', 'dtype': 'int64', 'values': [4, 5, 6]}, 'shape': (3,), 'dtype': 'int64', 'values': [4, 5, 6]}, 'name': 'b', 'unit': {'py/object': 'astropy.units.core.PrefixUnit', 'unit': 'km'}, 'format': None}, '__dict__': {}}, 'masked': False})

if __name__ == "__main__":
    test_funcs = [obj for name, obj in globals().items() if name.startswith('test_') and callable(obj)]
    for test_func in test_funcs:
        try:
            test_func()
            print(f"{test_func.__name__}: PASS")
        except Exception as e:
            print(f"{test_func.__name__}: FAIL")
            print(f'==== {test_func.__name__} ====')
            traceback.print_exc()
            print('=======================')
