def backward_slice(trace: list, start_event_id: int, target_var: str) -> list:
    """
    Performs backward dynamic slicing on an execution trace.

    Now considers both direct and inherited control dependencies.
    Also ensures the start event is considered for control dependency resolution,
    even if it doesn't define the target variable.

    Args:
        trace: List of event dictionaries from execution trace.
        start_event_id: The event ID where the slicing starts (e.g., where an error was observed).
        target_var: The variable of interest whose influencing statements we want to find.

    Returns:
        List of event dictionaries that form the dynamic backward slice.
        Events are included in the order they were encountered during backward traversal.
    """
    # Index trace by event_id for fast lookup
    trace_indexed = {event['event_id']: event for event in trace}

    # Initialize algorithm state
    influencing_vars = {target_var}
    control_dependent_events = {start_event_id}  # start event may need control explanation
    slice_result = []

    # Start from start_event_id and go backward to event_id 0
    current_id = start_event_id

    while current_id >= 0:
        stmt = trace_indexed[current_id]

        # Check if we should terminate early
        if len(influencing_vars) == 0 and len(control_dependent_events) == 0:
            break

        # --- 1. Interprocedural Data Dependency Check (NEW) ---
        # If this is a Function entry and target var is a parameter with a source
        if stmt['event_type'] == 'Function':
            parameters = stmt.get('parameters', {})
            param_sources = stmt.get('parameter_sources', {})
            matched_params = influencing_vars & set(parameters.keys())

            for param in matched_params:
                source_info = param_sources.get(param)
                if source_info and 'var' in source_info:
                    source_var = source_info['var']
                    # Propagate the source variable into influencing_vars
                    influencing_vars.add(source_var)
                    # Optional: if source event_id is known and valid, we could prioritize it,
                    # but backward traversal will naturally reach it.
                    # We include this Function event in the slice since it's part of the data flow.
                    slice_result.append(stmt)
                    # Also mark this event as control-dependent to ensure control deps are resolved
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






import json

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


def main():
    # --- CONFIGURE THESE VALUES ---
    jsonl_file_path = "/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/demonstration_trace.jsonl"      # Path to your .jsonl trace file
    start_event_id = 7                  # Example: event ID where error was observed
    target_var = "y"                     # Example: variable of interest

    # --- READ TRACE ---
    trace = read_trace_from_jsonl(jsonl_file_path)

    # --- PERFORM BACKWARD SLICING ---
    slice_result = backward_slice(trace, start_event_id, target_var)

    # --- OUTPUT RESULT ---
    print(f"Backward slice contains {len(slice_result)} events:")
    for event in slice_result:
        print(event)


# Assuming backward_slice is defined above or imported.
# If running as script, uncomment the line below:
if __name__ == "__main__":
    main()