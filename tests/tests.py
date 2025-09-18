from tracer import ExecutionTracer
from pathlib import Path

def test_simple_if(x):
    if x > 0:
        result = "positive"
    return result

def test_if_else(x):
    if x > 0:
        label = "positive"
    else:
        label = "non-positive"
    return label

def test_nested_if(x, y):
    if x > 0:
        if y > 0:
            msg = "both positive"
        else:
            msg = "x positive, y not"
    else:
        msg = "x not positive"
    return msg

def helper(value):
    if value == "special":
        flag = True
    else:
        flag = False
    return flag


def main_controller(x):
    if x > 10:
        outcome = helper("special")
    else:
        outcome = helper("normal")
    return outcome

def leaf(a):
    return a * 2

def middle(b):
    temp = leaf(b + 1)
    return temp - 1

def root(c):
    result = middle(c * 3)
    return result + 10

def processor(item):
    if item % 2 == 0:
        status = "even"
    else:
        status = "odd"
    return status

def run_loop(values):
    results = []
    for val in values:
        res = processor(val)
        results.append(res)
    return results

def test_try_except_finally(x):
    result = None
    try:
        if x == 0:
            raise ValueError()
        result = 100 / x
    except ValueError as e:
        result = f"ValueError: {str(e)}"
    except ZeroDivisionError:
        result = "Division by zero"
    finally:
        if result is None:
            result = "Unknown error occurred"
    return result

def test_while_loop(start):
    counter = start
    results = []
    while counter > 0:
        results.append(counter)
        counter -= 1
    return results

def risky_function(x):
    if x < 0:
        raise RuntimeError(f"Negative value not allowed: {x}")
    return x ** 2

def wrapper(a):
    try:
        return risky_function(a)
    except RuntimeError as e:
        return f"Handled: {str(e)}"


def top_level():
    results = []
    inputs = [2, -1, 3]
    for val in inputs:
        res = wrapper(val)
        results.append(res)
    return results


if __name__ == "__main__":
    RESULTS_DIR = Path("results")
    RESULTS_DIR.mkdir(exist_ok=True)

    # Test test_simple_if
    tracer = ExecutionTracer(output_file="results/trace_test_simple_if_1.jsonl")
    tracer.start_tracing()
    try:
        test_simple_if(5)  # x > 0 → "positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_simple_if_2.jsonl")
    tracer.start_tracing()
    try:
        test_simple_if(-3)  # x <= 0 → UnboundLocalError (to expose missing else)
    except Exception as e:
        pass  # expected error, we still want to capture trace
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test test_if_else
    tracer = ExecutionTracer(output_file="results/trace_test_if_else_1.jsonl")
    tracer.start_tracing()
    try:
        test_if_else(7)  # x > 0 → "positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_if_else_2.jsonl")
    tracer.start_tracing()
    try:
        test_if_else(0)  # x <= 0 → "non-positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_if_else_3.jsonl")
    tracer.start_tracing()
    try:
        test_if_else(-5)  # x <= 0 → "non-positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test test_nested_if
    tracer = ExecutionTracer(output_file="results/trace_test_nested_if_1.jsonl")
    tracer.start_tracing()
    try:
        test_nested_if(5, 3)  # x>0, y>0 → "both positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_nested_if_2.jsonl")
    tracer.start_tracing()
    try:
        test_nested_if(5, -2)  # x>0, y<=0 → "x positive, y not"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_nested_if_3.jsonl")
    tracer.start_tracing()
    try:
        test_nested_if(-1, 4)  # x<=0 → "x not positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_nested_if_4.jsonl")
    tracer.start_tracing()
    try:
        test_nested_if(0, 0)  # x<=0 → "x not positive"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test helper
    tracer = ExecutionTracer(output_file="results/trace_helper_1.jsonl")
    tracer.start_tracing()
    try:
        helper("special")  # value == "special" → True
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_helper_2.jsonl")
    tracer.start_tracing()
    try:
        helper("normal")  # value != "special" → False
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_helper_3.jsonl")
    tracer.start_tracing()
    try:
        helper("")  # value != "special" → False
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test main_controller
    tracer = ExecutionTracer(output_file="results/trace_main_controller_1.jsonl")
    tracer.start_tracing()
    try:
        main_controller(15)  # x > 10 → helper("special") → True
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_main_controller_2.jsonl")
    tracer.start_tracing()
    try:
        main_controller(5)  # x <= 10 → helper("normal") → False
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_main_controller_3.jsonl")
    tracer.start_tracing()
    try:
        main_controller(10)  # x <= 10 → helper("normal") → False
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test leaf
    tracer = ExecutionTracer(output_file="results/trace_leaf_1.jsonl")
    tracer.start_tracing()
    try:
        leaf(3)  # a * 2 → 6
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_leaf_2.jsonl")
    tracer.start_tracing()
    try:
        leaf(0)  # a * 2 → 0
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_leaf_3.jsonl")
    tracer.start_tracing()
    try:
        leaf(-2)  # a * 2 → -4
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test middle
    tracer = ExecutionTracer(output_file="results/trace_middle_1.jsonl")
    tracer.start_tracing()
    try:
        middle(2)  # leaf(3)=6 → 5
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_middle_2.jsonl")
    tracer.start_tracing()
    try:
        middle(0)  # leaf(1)=2 → 1
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_middle_3.jsonl")
    tracer.start_tracing()
    try:
        middle(-1)  # leaf(0)=0 → -1
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test root
    tracer = ExecutionTracer(output_file="results/trace_root_1.jsonl")
    tracer.start_tracing()
    try:
        root(1)  # middle(3) → 7 → 17
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_root_2.jsonl")
    tracer.start_tracing()
    try:
        root(0)  # middle(0) → 1 → 11
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_root_3.jsonl")
    tracer.start_tracing()
    try:
        root(-1)  # middle(-3) → -5 → 5
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test processor
    tracer = ExecutionTracer(output_file="results/trace_processor_1.jsonl")
    tracer.start_tracing()
    try:
        processor(4)  # even → "even"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_processor_2.jsonl")
    tracer.start_tracing()
    try:
        processor(7)  # odd → "odd"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_processor_3.jsonl")
    tracer.start_tracing()
    try:
        processor(0)  # even → "even"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test run_loop
    tracer = ExecutionTracer(output_file="results/trace_run_loop_1.jsonl")
    tracer.start_tracing()
    try:
        run_loop([1, 2, 3])  # ["odd", "even", "odd"]
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_run_loop_2.jsonl")
    tracer.start_tracing()
    try:
        run_loop([])  # []
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_run_loop_3.jsonl")
    tracer.start_tracing()
    try:
        run_loop([0, -1, 4])  # ["even", "odd", "even"]
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test test_try_except_finally
    tracer = ExecutionTracer(output_file="results/trace_test_try_except_finally_1.jsonl")
    tracer.start_tracing()
    try:
        test_try_except_finally(5)  # normal → 20.0
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_try_except_finally_2.jsonl")
    tracer.start_tracing()
    try:
        test_try_except_finally(0)  # ZeroDivisionError → "Division by zero"
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_try_except_finally_3.jsonl")
    tracer.start_tracing()
    try:
        test_try_except_finally(-3)  # normal → -33.333...
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_try_except_finally_4.jsonl")
    tracer.start_tracing()
    try:
        test_try_except_finally(100)  # normal → 1.0
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_try_except_finally_5.jsonl")
    tracer.start_tracing()
    try:
        test_try_except_finally('a')  # TypeError → "Unknown error occurred"
    except:
        pass
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test test_while_loop
    tracer = ExecutionTracer(output_file="results/trace_test_while_loop_1.jsonl")
    tracer.start_tracing()
    try:
        test_while_loop(3)  # [3, 2, 1]
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_while_loop_2.jsonl")
    tracer.start_tracing()
    try:
        test_while_loop(0)  # []
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_while_loop_3.jsonl")
    tracer.start_tracing()
    try:
        test_while_loop(1)  # [1]
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_test_while_loop_4.jsonl")
    tracer.start_tracing()
    try:
        test_while_loop(-2)  # []
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test risky_function (uncaught — will raise, but trace captured)
    tracer = ExecutionTracer(output_file="results/trace_risky_function_1.jsonl")
    tracer.start_tracing()
    try:
        risky_function(4)  # 16
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_risky_function_2.jsonl")
    tracer.start_tracing()
    try:
        risky_function(0)  # 0
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_risky_function_3.jsonl")
    tracer.start_tracing()
    try:
        risky_function(-2)  # raises RuntimeError — trace still captured
    except RuntimeError:
        pass
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test wrapper
    tracer = ExecutionTracer(output_file="results/trace_wrapper_1.jsonl")
    tracer.start_tracing()
    try:
        wrapper(3)  # 9
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_wrapper_2.jsonl")
    tracer.start_tracing()
    try:
        wrapper(-2)  # "Handled: ..."
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    tracer = ExecutionTracer(output_file="results/trace_wrapper_3.jsonl")
    tracer.start_tracing()
    try:
        wrapper(0)  # 0
    finally:
        tracer.stop_tracing()
        tracer.save_trace()

    # Test top_level
    tracer = ExecutionTracer(output_file="results/trace_top_level.jsonl")
    tracer.start_tracing()
    try:
        top_level()  # [4, "Handled: ...", 9]
    finally:
        tracer.stop_tracing()
        tracer.save_trace()