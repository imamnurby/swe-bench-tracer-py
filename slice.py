def backward_slice(trace: list, start_event_id: int, target_var: str) -> list:
    """
    Performs backward dynamic slicing on an execution trace.

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
    influencing_vars = {target_var}     # Variables whose origins we need to trace
    control_dependent_events = set()    # Event IDs whose control dependencies need explaining
    slice_result = []                   # Result slice: list of event dicts in traversal order

    # Start from start_event_id and go backward to event_id 0
    current_id = start_event_id

    while current_id >= 0:
        stmt = trace_indexed[current_id]

        # Check if we should terminate early
        if len(influencing_vars) == 0 and len(control_dependent_events) == 0:
            break

        # --- 1. Dynamic Data Dependency Check ---
        # If this statement defines any variable currently in influencing_vars
        vars_defined = set(stmt.get('vars_defined', []))
        if vars_defined & influencing_vars:  # Intersection: any defined var is in influencing_vars?
            # Remove defined vars from influencing_vars
            influencing_vars -= vars_defined
            # Add all used vars to influencing_vars (to trace their origins)
            vars_used = stmt.get('vars_used', [])
            influencing_vars.update(vars_used)
            # Add this stmt to slice_result
            slice_result.append(stmt)
            # Add this stmt's event_id to control_dependent_events (its control flow may need explaining)
            control_dependent_events.add(current_id)

        # --- 2. Dynamic Control Dependency Check ---
        # Check if this statement is a control decision point for any event in control_dependent_events
        controlling = False
        dependent_events_to_remove = set()

        for dep_id in control_dependent_events:
            dep_event = trace_indexed[dep_id]
            ctrl_deps = dep_event.get('control_dependencies', [])
            # Check if this stmt (current_id) controls dep_event (via -current_id or current_id)
            if (-current_id in ctrl_deps) or (current_id in ctrl_deps):
                controlling = True
                dependent_events_to_remove.add(dep_id)

        if controlling:
            # Remove those now-explained events from control_dependent_events
            control_dependent_events -= dependent_events_to_remove
            # Add all used vars of this control stmt to influencing_vars (their values influenced the decision)
            vars_used = stmt.get('vars_used', [])
            influencing_vars.update(vars_used)
            # Add this stmt to slice_result and control_dependent_events
            slice_result.append(stmt)
            control_dependent_events.add(current_id)

        # Move to previous event
        current_id -= 1

    return slice_result