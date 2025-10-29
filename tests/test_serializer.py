import traceback

from tracer.serializer import serialize, deserialize

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
    assert serialized == {'py/object': '__main__.test_dict_of_funcs_in_class.<locals>.A', 'data': {'key': {'py/function': '__main__.test_dict_of_funcs_in_class.<locals>.dummy_func'}}}

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
