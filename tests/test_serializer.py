import traceback
import numpy as np

from collections.abc import Sequence
from tracer.serializer import serialize, deserialize

def assert_equals(obj, expected):
    assert obj == expected, f"Provided: {obj}\nExpected: {expected}"

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
    assert_equals(serialized, {'py/object': '__main__.test_dict_of_funcs_in_class.<locals>.A', 'data': {'key': {'py/function': '__main__.test_dict_of_funcs_in_class.<locals>.dummy_func'}}})

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
    
    assert_equals(serialized, {'py/reduce': [{'py/function': 'numpy._core.multiarray._reconstruct'}, {'py/tuple': [{'py/type': '__main__.test_subclass_of_registered_type.<locals>.MyArray'}, {'py/tuple': [0]}, {'py/b64': 'Yg=='}]}, {'py/tuple': [1, {'py/tuple': [3]}, {'py/reduce': [{'py/type': 'numpy.dtype'}, {'py/tuple': ['i8', False, True]}, {'py/tuple': [3, '<', None, None, None, -1, -1, 0]}]}, False, {'py/b64': 'AQAAAAAAAAACAAAAAAAAAAMAAAAAAAAA'}]}]})

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
    expected_output = "<Unserializable Sequence object>"
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
