import json
from typing import List, Dict, Tuple

def map_call_sites_to_return_events(trace: List[Dict]) -> Dict[int, Dict]:
    """
    Creates a mapping from a call site event ID to its corresponding 'Return' event.

    This is essential for tracing data dependencies from a function's return value
    back to the variable it's assigned to at the call site.

    It works by:
    1. Using a stack to pair 'Function' entry events with their 'Return' events.
    2. Assuming the line event that performs the call occurs immediately before
       the corresponding 'Function' entry event in the trace.

    Args:
        trace: The full execution trace.

    Returns:
        A dictionary where keys are the event_id of a 'Line' event that calls a function,
        and values are the corresponding 'Return' event dictionary for that function call.
    """
    call_stack = []
    func_event_to_return_map = {}

    for event in trace:
        if event['event_type'] == 'Function':
            call_stack.append(event['event_id'])
        elif event['event_type'] == 'Return':
            if call_stack:
                func_event_id = call_stack.pop()
                func_event_to_return_map[func_event_id] = event

    call_site_to_return_map = {}
    for func_event_id, return_event in func_event_to_return_map.items():
        if func_event_id > 0:
            # The line event making the call is assumed to be right before the function entry event
            call_site_event_id = func_event_id - 1
            call_site_to_return_map[call_site_event_id] = return_event

    return call_site_to_return_map

def build_scope_map(trace: List[Dict]) -> Dict[int, int]:
    """
    Builds a map from each event_id to its corresponding function scope_id.

    The scope_id is defined as the event_id of the 'Function' entry event
    for the function call that the event is a part of. This handles nested
    calls correctly using a stack.

    Args:
        trace: The full execution trace.

    Returns:
        A dictionary mapping event_id -> scope_id.
    """
    scope_map = {}
    scope_stack = []  # Stack of scope_ids (function entry event_ids)

    # We need a way to link Return events back to their Function events
    # to know when to pop the stack.
    call_stack = []
    return_to_func_map = {}
    for event in trace:
        if event['event_type'] == 'Function':
            call_stack.append(event['event_id'])
        elif event['event_type'] == 'Return':
            if call_stack:
                func_event_id = call_stack.pop()
                return_to_func_map[event['event_id']] = func_event_id

    # Now, build the scope map
    for event in trace:
        event_id = event['event_id']
        
        if event['event_type'] == 'Return':
            if scope_stack and event_id in return_to_func_map:
                # Check if this return corresponds to the current scope
                if return_to_func_map[event_id] == scope_stack[-1]:
                    # Assign scope before popping
                    scope_map[event_id] = scope_stack[-1]
                    scope_stack.pop()
                else: # Mismatched return, assign scope from top of stack anyway
                    if scope_stack:
                        scope_map[event_id] = scope_stack[-1]
            elif scope_stack: # Fallback for returns without a matching function
                 scope_map[event_id] = scope_stack[-1]
        
        else: # Not a Return event
            if scope_stack:
                scope_map[event_id] = scope_stack[-1]

            if event['event_type'] == 'Function':
                scope_stack.append(event_id)
                # A function's entry event is part of its own scope
                scope_map[event_id] = event_id

    return scope_map

def backward_slice(trace: List[Dict], start_event_id: int, target_vars: List[str]) -> List[Dict]:
    """
    Performs backward dynamic slicing on an execution trace using a multi-pass approach
    to correctly handle interprocedural data dependencies.

    Args:
        trace: List of event dictionaries from execution trace.
        start_event_id: The event ID where the slicing starts.
        target_vars: The initial list of variables of interest.

    Returns:
        List of event dictionaries that form the dynamic backward slice, ordered
        from the most recent event to the oldest.
    """
    trace_indexed = {event['event_id']: event for event in trace}
    call_site_to_return_map = map_call_sites_to_return_events(trace)
    
    scope_map = build_scope_map(trace)

    # The initial variables of interest belong to the scope of the start event.
    start_scope_id = scope_map.get(start_event_id)
    if start_scope_id is None:
        start_scope_id = -1 # Use -1 to denote the global scope
    
    # Convert initial target_vars to scoped variables
    cumulative_influencing_vars = {(var, start_scope_id) for var in target_vars}

    slice_event_ids = set()
    
    # --- Multi-Pass Slicing Loop ---
    # This loop continues until a full backward pass finds no new influential variables.
    # The main idea is we try to do the backward pass multiple times, each time we record the influencing variables to newly_discovered_vars
    # We also record cumulative_influencing_vars as the union of all influencing variables found so far
    # If in a pass, we find no new influencing variables (newly_discovered_vars - cumulative_influencing_vars) is empty --> converge
    # If converge, then we are done and exit the loop
    while True:
        pass_influencing_vars = cumulative_influencing_vars.copy()
        newly_discovered_vars = set()
        
        # We start each pass with the same initial control dependency.
        control_dependent_events = {start_event_id}
        
        # --- Single Backward Pass ---
        for current_id in range(start_event_id, -1, -1):
            stmt = trace_indexed[current_id]

            # Criteria for including the current statement in the slice
            is_data_dependent = False
            is_control_dependent = False

            # 1. Dynamic Data Dependency Check
            current_scope_id = scope_map.get(current_id, -1) # Default to global scope
            vars_defined = set(stmt.get('vars_defined', []))
            
            # Check if this statement defines any variable we are currently looking for in this specific scope
            scoped_vars_defined = {(var, current_scope_id) for var in vars_defined}
            if scoped_vars_defined & pass_influencing_vars:
                is_data_dependent = True
                pass_influencing_vars -= scoped_vars_defined
                
                # Add the variables used by this statement (in its scope) as new targets
                vars_used = stmt.get('vars_used', [])
                scoped_vars_used = {(var, current_scope_id) for var in vars_used}
                pass_influencing_vars.update(scoped_vars_used)
                newly_discovered_vars.update(scoped_vars_used)
                
                # Check for interprocedural data dependency through function returns
                if current_id in call_site_to_return_map:
                    return_event = call_site_to_return_map[current_id]
                    return_scope_id = scope_map.get(return_event['event_id'], -1)
                    return_vars_used = return_event.get('vars_used', [])
                    
                    scoped_return_vars = {(var, return_scope_id) for var in return_vars_used}
                    pass_influencing_vars.update(scoped_return_vars)
                    newly_discovered_vars.update(scoped_return_vars)

            # 2. Dynamic Control Dependency Check
            dependent_events_to_remove = set()
            for dep_id in control_dependent_events:
                dep_event = trace_indexed[dep_id]
                all_ctrl_deps = set(dep_event.get('control_dependencies', [])) | \
                               set(dep_event.get('inherited_control_dependencies', []))
                if current_id in all_ctrl_deps or -current_id in all_ctrl_deps:
                    is_control_dependent = True
                    dependent_events_to_remove.add(dep_id)
            
            if is_control_dependent:
                control_dependent_events -= dependent_events_to_remove
                vars_used = stmt.get('vars_used', [])
                # Also use the current_scope_id defined in the data dependency check section
                scoped_vars_used = {(var, current_scope_id) for var in vars_used}
                pass_influencing_vars.update(scoped_vars_used)
                newly_discovered_vars.update(scoped_vars_used)

            # Add statement to slice if it meets either criterion
            if is_data_dependent or is_control_dependent:
                slice_event_ids.add(current_id)
                control_dependent_events.add(current_id) # The statement itself becomes a point of control interest

        # --- Check for Convergence ---
        # If this pass did not add any new variables to our cumulative set, we are done.
        if not (newly_discovered_vars - cumulative_influencing_vars):
            break
        
        # Otherwise, update the cumulative set and run another pass.
        cumulative_influencing_vars.update(newly_discovered_vars)

    # --- Finalize Slice ---
    # Retrieve the full event dictionaries for the IDs in the slice.
    # Sort them in reverse chronological order to match the backward traversal.
    slice_result = [trace_indexed[id] for id in sorted(list(slice_event_ids), reverse=True)]
    
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