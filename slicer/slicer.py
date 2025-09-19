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

def infer_slicing_criteria(trace: List[str], start_event_id: int, target_vars: List[str]):
    """
    Infers the slicing criteria (start_event_id and target_vars) if they are not provided.

    - If start_event_id is None, it defaults to the last event in the trace.
    - If target_vars is None, it searches backwards from the start_event_id
      to find the first event with 'vars_used'.

    Args:
        trace: The full execution trace.
        start_event_id: The starting event ID (can be None).
        target_vars: The target variables (can be None).

    Returns:
        A tuple (final_start_event_id, final_target_vars).
        Returns (None, None) if criteria cannot be inferred.
    """
    if not trace:
        print("Trace is empty. Cannot infer slicing criteria.")
        return None, None

    # Infer start_event_id if not provided
    if start_event_id is None:
        start_event_id = trace[-1]['event_id']
        print(f"No start_event_id provided. Defaulting to the last event: {start_event_id}")

    # Infer target_vars if not provided
    if target_vars is None:
        print("No target_vars provided. Searching backwards for the first event with 'vars_used'...")
        
        # Index trace by event_id for fast lookup
        trace_indexed = {event['event_id']: event for event in trace}
        
        inferred = False
        # Start searching from the current start_event_id backwards
        for i in range(start_event_id, -1, -1):
            event = trace_indexed.get(i)
            if event and event.get('vars_used'):
                target_vars = event.get('vars_used')
                start_event_id = event['event_id']  # This becomes our new, precise start point
                print(f"Found slicing criteria at event {start_event_id}: target_vars = {target_vars}")
                inferred = True
                break
        
        if not inferred:
            print("Could not infer target_vars. No event with 'vars_used' found in the trace.")
            return None, None

    return start_event_id, target_vars


def execute_backward_slice(jsonl_file_path: str, start_event_id: int, target_vars: List[str])->List[str]:
    # --- READ TRACE ---
    trace = read_trace_from_jsonl(jsonl_file_path)

    # --- INFER SLICING CRITERIA IF NOT PROVIDED ---
    start_event_id, target_vars = infer_slicing_criteria(trace, start_event_id, target_vars)

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