import json
from typing import List

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
        # If this is a Function entry and target var is a parameter with source(s)
        if stmt['event_type'] == 'Function':
            parameters = stmt.get('parameters', {})
            param_sources = stmt.get('parameter_sources', {})
            matched_params = influencing_vars & set(parameters.keys())

            for param in matched_params:
                sources = param_sources.get(param, [])
                # Ensure it's treated as a list (even if old format was single dict)
                if isinstance(sources, dict):
                    sources = [sources]  # backwards compatibility, if needed
                elif not isinstance(sources, list):
                    sources = []  # fallback

                for source_info in sources:
                    if isinstance(source_info, dict) and 'var' in source_info:
                        source_var = source_info['var']
                        influencing_vars.add(source_var)
                        # Optional: use source_info['event_id'] for directed jump (not needed in backward walk)

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

def read_trace_from_jsonl(jsonl_path: str) -> list:
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
            if line:  # Skip empty lines
                event = json.loads(line)
                trace.append(event)
    return trace

def infer_slicing_criteria_from_event_type(trace: List[str], target_event_type: str):
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
    # Part 2: Find the slicing event and its criteria
    print("Searching backwards from anchor event for the first event with 'vars_used'...")
    
    # Index trace by event_id for fast lookup
    trace_indexed = {event['event_id']: event for event in trace}
    
    # Start searching from the anchor_event's id backwards
    for i in range(start_event_id, -1, -1):
        event = trace_indexed.get(i)
        # Check for a non-empty vars_used list
        if event and event.get('vars_used'):
            final_event_id = event['event_id']
            final_target_vars = event['vars_used']
            statement = event.get('statement', '')
            function_name = event.get('function_name', '')
            filepath = event.get('filepath', '')
            
            print(f"Found slicing criteria at event {final_event_id}: target_vars = {final_target_vars}")
            return final_event_id, final_target_vars, statement, function_name, filepath
    
    # If no event with 'vars_used' was found
    print("Could not infer slicing criteria. No event with 'vars_used' found backwards from the anchor.")
    return None, None, None, None, None


def execute_backward_slice(jsonl_file_path: str, start_event_id: int, target_vars: List[str])->List[str]:
    # --- READ TRACE ---
    trace = read_trace_from_jsonl(jsonl_file_path)

    # --- INFER SLICING CRITERIA IF NOT PROVIDED ---
    start_event_id, target_vars = infer_slicing_criteria_from_event_type(trace, start_event_id, target_vars)

    if start_event_id is None or target_vars is None:
        print("Could not determine slicing criteria. Exiting.")
        return

    # Ensure target_vars is a list, as backward_slice expects it
    if isinstance(target_vars, str):
        target_vars = [target_vars]
        
    slice_result = backward_slice(trace, start_event_id, target_vars)

    # --- OUTPUT RESULT ---
    print(f"\nBackward slice for {target_vars} starting from event {start_event_id} contains {len(slice_result)} events:")
    for event in slice_result:
        print(event)
    
    return slice_result