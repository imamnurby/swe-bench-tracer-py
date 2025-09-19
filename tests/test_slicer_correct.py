from slicer import execute_backward_slice_for_correct_code
import pprint as pp


if __name__ == "__main__":
    json_filepath = "/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tests/sample_programs/correct.jsonl"
    target_statement = '    assert processed == "Category: NON-POSITIVE", "Failed: zero should be non-positive"'
    target_filepath = "/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tests/sample_programs/correct.py"
    target_function_name = "__main__:run_tests"
    slice_result = execute_backward_slice_for_correct_code(json_filepath, target_filepath, target_function_name, target_statement)

    for event in slice_result:
        pp.pprint(event)   