from slicer import execute_backward_slice_for_buggy_code
import json


if __name__ == "__main__":
    json_filepath = "/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tests/astropy__astropy-12907/trace_buggy.jsonl"
    slice_result, starting_statement, starting_function_name, starting_filepath = execute_backward_slice_for_buggy_code(json_filepath, target_event_type="Exception")
    
    with open("/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tests/astropy__astropy-12907/buggy_slice.result", 'w', encoding='utf-8') as f:
        for event in slice_result:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    