from slicer import execute_backward_slice_for_buggy_code
import pprint as pp


if __name__ == "__main__":
    json_filepath = "/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tests/sample_programs/buggy.jsonl"
    slice_result, starting_statement, starting_function_name, starting_filepath = execute_backward_slice_for_buggy_code(json_filepath, target_event_type="Exception")

    assert len(slice_result) == 4
    expected_event_ids = (10, 4, 3, 2)
    result_event_ids = []
    for expected_event_ids, event in zip(expected_event_ids, slice_result):
        assert(expected_event_ids == event.get("event_id"))
        pp.pprint(event)
        
    pp.pprint(f"Slicing started from the statement: {starting_statement} in function {starting_function_name} located at {starting_filepath}")
    