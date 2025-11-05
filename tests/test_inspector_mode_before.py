# NOTE: To make line numbers consistent, only append new test code before `if __name__ == "__main__":`
import os
import traceback

from tracer import ExpressionInspector as Inspector
from tracer.protocol import InspectionResult as Result

FILE_PATH = os.path.abspath(__file__)

def assert_equals(obj, expected):
    assert obj == expected, f"Provided: {obj}\nExpected: {expected}"

def test_basic_function():
    def func():
        a = 10
        b = 20
        c = a + b
        return c
    with Inspector(FILE_PATH, 18, 'c', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 30)

def test_function_with_exception_handled():
    def func():
        a = 10
        b = 20
        try:
            assert False, "Intentional Failure"
        except AssertionError:
            b = 30
        c = a + b
        return c
    with Inspector(FILE_PATH, 33, 'c', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 40)
    with Inspector(FILE_PATH, 31, 'b', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.exception, None)
    assert_equals(result.value, 20)

def test_function_with_exception_unhandled():
    def func():
        a = 10
        b = 20
        assert False, "Intentional Failure"
        c = a + b
        return c
    with Inspector(FILE_PATH, 50, 'c', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, None)
    assert_equals(result.exception.stage, 'exception before breakpoint')
    assert_equals(result.exception.type, 'AssertionError')

def test_more_complex_expr1():
    def func():
        a = [1, 2, 3]
        b = [4, 5, 6]
        c = a + b
        return c
    with Inspector(FILE_PATH, 63, 'len(c)', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 6)
    with Inspector(FILE_PATH, 63, 'c[3]', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 4)

def test_variable_scope():
    def func1():
        a = 10
        def inner():
            b = 20
            return a + b
        c = inner()
        return c
    with Inspector(FILE_PATH, 80, 'b', mode='before') as inspector:
        func1()
    result = Result(**inspector.result)
    assert_equals(result.value, None)
    assert_equals(result.exception.type, 'NameError')
    with Inspector(FILE_PATH, 78, 'a', mode='before') as inspector:
        func1()
    result = Result(**inspector.result)
    assert_equals(result.value, 10)
    
    def func2():
        a = 10
        if True:
            b = 20
        c = a + b
        return c
    with Inspector(FILE_PATH, 96, 'b', mode='before') as inspector:
        func2()
    result = Result(**inspector.result)
    assert_equals(result.value, 20)

def test_count_parameter():
    def func():
        x = 0
        for i in range(5):
            x = i + 1
        return x
    with Inspector(FILE_PATH, 106, 'x', count=3, mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 2)

def test_more_complex_expr2():
    def func():
        class MyClass:
            def __init__(self, val):
                self.val = val
            def get_val(self):
                return self.val
        obj = MyClass(42)
        return obj
    with Inspector(FILE_PATH, 121, 'obj.get_val()', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 42)

def test_library_call():
    import numpy as np
    def func():
        a = np.array([1, 2, 3])
        b = np.array([4, 5, 6])
        c = a + b
        return c
    with Inspector(FILE_PATH, 133, 'c.tolist()', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, [5, 7, 9])
    with Inspector(FILE_PATH, 133, 'int(np.sum(c))', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 21)

def test_return_inspection():
    def func():
        a = 5
        b = 10
        return a * b
    with Inspector(FILE_PATH, 147, '__return__', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 50)
    with Inspector(FILE_PATH, 147, '__return__ * 2', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 100)

def test_function_call_in_return():
    def helper(x):
        return x + 1
    def func():
        a = 5
        return helper(a)
    with Inspector(FILE_PATH, 162, '__return__', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 6)
    with Inspector(FILE_PATH, 162, 'helper(__return__)', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 7)
    with Inspector(FILE_PATH, 159, '__return__', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 6)

def test_nested_call_in_return():
    def helper1(x):
        return x + 2
    def helper2(y):
        return helper1(y) * 3
    def func():
        a = 4
        return helper2(a)
    with Inspector(FILE_PATH, 183, '__return__', mode='before') as inspector:
        func()
    result = Result(**inspector.result)
    assert_equals(result.value, 18)

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