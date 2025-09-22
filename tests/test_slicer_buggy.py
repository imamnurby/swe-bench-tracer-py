from slicer import execute_backward_slice_for_buggy_code
import json


if __name__ == "__main__":
    json_filepath = "/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tests/sample_programs/buggy.jsonl"
    slice_result, starting_statement, starting_function_name, starting_filepath = execute_backward_slice_for_buggy_code(json_filepath, target_event_type="Exception")
    
    with open("sample_programs/buggy_slice.result", 'w', encoding='utf-8') as f:
        for event in slice_result:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    