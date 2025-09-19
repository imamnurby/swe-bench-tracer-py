import json
from typing import List, Dict, Tuple

def backward_slice(trace: List[str], start_event_id: int, target_vars: List[str]) -> List[str]:
    """
    Performs backward dynamic slicing on an execution trace.

    Now considers both direct and inherited control dependencies.
    Also ensures the start event is considered for control dependency resolution,
    even if it doesn't define the target variable.

    Args:
        trace: List of event dictionaries from execution trace.
        start_event_id: The event ID where the slicing starts (e.g., where an error was observed).
        target_vars: The list of variables of interest whose influencing statements we want to find.

    Returns:
        List of event dictionaries that form the dynamic backward slice.
        Events are included in the order they were encountered during backward traversal.
    """
    # Index trace by event_id for fast lookup
    trace_indexed = {event['event_id']: event for event in trace}

    # Initialize algorithm state
    influencing_vars = set(target_vars)
    control_dependent_events = {start_event_id}  # start event may need control explanation
    slice_result = []

    # Start from start_event_id and go backward to event_id 0
    current_id = start_event_id

    while current_id >= 0:
        stmt = trace_indexed[current_id]

        # Check if we should terminate early
        if len(influencing_vars) == 0 and len(control_dependent_events) == 0:
            break

        # --- 1. Interprocedural Data Dependency Check ---
        if stmt['event_type'] == 'Function':
            parameters = stmt.get('parameters', {})
            param_sources = stmt.get('parameter_sources', {})
            matched_params = influencing_vars & set(parameters.keys())

            for param in matched_params:
                sources = param_sources.get(param, [])
                if isinstance(sources, dict):
                    sources = [sources]
                elif not isinstance(sources, list):
                    sources = []

                for source_info in sources:
                    if isinstance(source_info, dict) and 'var' in source_info:
                        source_var = source_info['var']
                        influencing_vars.add(source_var)

                # Include this Function event in the slice — it’s part of the data flow
                slice_result.append(stmt)
                control_dependent_events.add(current_id)

        # --- 2. Dynamic Data Dependency Check ---
        vars_defined = set(stmt.get('vars_defined', []))
        if vars_defined & influencing_vars:
            influencing_vars -= vars_defined
            vars_used = stmt.get('vars_used', [])
            influencing_vars.update(vars_used)
            slice_result.append(stmt)
            control_dependent_events.add(current_id)

        # --- 3. Dynamic Control Dependency Check ---
        controlling = False
        dependent_events_to_remove = set()

        for dep_id in control_dependent_events:
            dep_event = trace_indexed[dep_id]
            all_ctrl_deps = set(dep_event.get('control_dependencies', [])) | \
                           set(dep_event.get('inherited_control_dependencies', []))

            if current_id in all_ctrl_deps or -current_id in all_ctrl_deps:
                controlling = True
                dependent_events_to_remove.add(dep_id)

        if controlling:
            control_dependent_events -= dependent_events_to_remove
            vars_used = stmt.get('vars_used', [])
            influencing_vars.update(vars_used)
            slice_result.append(stmt)
            control_dependent_events.add(current_id)

        current_id -= 1

    return slice_result

def read_trace_from_jsonl(jsonl_path: str) -> List[Dict]:
    """
    Reads an execution trace from a .jsonl file.
    Each line in the file should be a JSON object representing one event.

    Args:
        jsonl_path: Path to the .jsonl file.

    Returns:
        List of event dictionaries.
    """
    trace = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                event = json.loads(line)
                trace.append(event)
    return trace

def infer_slicing_criteria_from_event_type(trace: List[str], target_event_type: str)->Tuple[int, str, str, str]:
    """
    Infers slicing criteria by finding a relevant event in the trace.

    The process is as follows:
    1. Find an anchor event:
    2. Find the slicing event:
       - Search backwards from the anchor event to find the first event with a
         non-empty 'vars_used' list. This becomes the slicing event.

    Args:
        trace: The full execution trace.
        target_event_type: The type of event to search for (e.g., "Exception").

    Returns:
        A tuple (event_id, target_vars, statement, function_name, filepath).
        Returns (None, None, None, None, None) if criteria cannot be inferred.
    """
    if not trace:
        print("Trace is empty. Cannot infer slicing criteria.")
        return None, None, None, None, None

    # Part 1: Find the anchor event
    anchor_event = None
    print(f"Searching backwards for the latest event of type '{target_event_type}'...")
    for event in reversed(trace):
        if event.get('event_type') == target_event_type:
            anchor_event = event
            break
    if not anchor_event:
        print(f"Error: No event of type '{target_event_type}' found in the trace.")
        return None, None, None, None, None
    
    print(f"Anchor event found: ID {anchor_event['event_id']}, Type '{anchor_event['event_type']}'")
    start_event_id = anchor_event['event_id']

    # Part 2: Find the slicing event and its criteria
    print("Searching backwards from anchor event for the first event with 'vars_used'...")
    
    trace_indexed = {event['event_id']: event for event in trace}
    
    for i in range(start_event_id, -1, -1):
        event = trace_indexed.get(i)
        if event and event.get('vars_used'):
            final_event_id = event['event_id']
            final_target_vars = event['vars_used']
            statement = event.get('statement', '')
            function_name = event.get('function_name', '')
            filepath = event.get('filepath', '')
            
            print(f"Found slicing criteria at event {final_event_id}: target_vars = {final_target_vars}")
            return final_event_id, final_target_vars, statement, function_name, filepath
    
    print("Could not infer slicing criteria. No event with 'vars_used' found backwards from the anchor.")
    return None, None, None, None, None


def execute_backward_slice_for_buggy_code(jsonl_file_path: str, target_event_type: str)->Tuple[Dict, str, str, str]:
    """
    Executes a backward program slice on a trace from a buggy code execution.
    Args:
        jsonl_file_path (str): The path to the JSONL file containing the
            execution trace.
        target_event_type (str): The type of event to use as an anchor for
            inferring the slicing criteria. For example, 'Exception'.

    Returns:
        tuple: A tuple containing four elements:
            - slice_result (List[Dict]): The backward slice, which is a list of
              the relevant trace events.
            - statement (str): The source code statement from which the slice
              was initiated.
            - function_name (str): The name of the function containing the
              slicing statement.
            - filepath (str): The path to the source file containing the
              slicing statement.
        Returns None if the slicing criteria cannot be successfully inferred.
    """
    trace = read_trace_from_jsonl(jsonl_file_path)

    start_event_id, target_vars, statement, function_name, filepath = infer_slicing_criteria_from_event_type(trace, target_event_type)

    if start_event_id is None or target_vars is None:
        print("Could not determine slicing criteria. Exiting.")
        return
        
    slice_result = backward_slice(trace, start_event_id, target_vars)

    return slice_result, statement, function_name, filepath

def infer_slicing_criteria_from_statement(trace: List[dict], target_filepath: str, target_function_name: str, target_statement: str) -> Dict:
    """
    Searches a trace backwards for a specific statement to use as a slicing criterion.

    Args:
        trace (List[dict]): The full execution trace.
        target_filepath (str): The absolute path of the source file to search for.
        target_function_name (str): The name of the function to search within.
        target_statement (str): The source code of the statement to find.
            Whitespace is stripped for comparison.

    Returns:
        dict: The complete event dictionary of the found slicing event, or None
              if no matching event was found.
    """
    print(f"Searching for statement: '{target_statement.strip()}' in {target_function_name}")
    
    for event in reversed(trace):
        if (event.get('vars_used') and
            event.get('filepath') == target_filepath and
            event.get('function_name') == target_function_name and
            event.get('statement', '').strip() == target_statement.strip()):
            
            print(f"Found matching event for slicing at ID: {event['event_id']}")
            return event

    return None

def execute_backward_slice_for_correct_code(jsonl_filepath: str, target_filepath: str, target_function_name: str, target_statement: str)->List[Dict]:
    """
    Finds the last execution of a specific line of code and performs a backward slice.

    Args:
        jsonl_filepath (str): The path to the JSONL file containing the
            execution trace.
        target_filepath (str): The absolute path of the source file to search for.
        target_function_name (str): The name of the function to search within.
        target_statement (str): The exact source code of the statement to find.
            Whitespace will be stripped for comparison.

    Returns:
        List[Dict]: The backward slice, which is a list of the relevant trace
        events. Returns None if no matching event could be found in the trace.
    """
    trace = read_trace_from_jsonl(jsonl_filepath)
    if not trace:
        print("Trace is empty or could not be read.")
        return None

    slicing_event = infer_slicing_criteria_from_statement(
        trace, target_filepath, target_function_name, target_statement
    )
    
    if slicing_event:
        start_event_id = slicing_event['event_id']
        target_vars = slicing_event['vars_used']
        
        if isinstance(target_vars, str):
            target_vars = [target_vars]

        slice_result = backward_slice(trace, start_event_id, target_vars)
        return slice_result
    else:
        print("Could not find a matching event with the specified criteria and non-empty 'vars_used'.")
        return None