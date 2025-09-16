def backward_slice(trace: list, start_event_id: int, target_var: str) -> list:
    """
    Performs backward dynamic slicing on an execution trace.

    Args:
        trace: List of event dictionaries from execution trace.
        start_event_id: The event ID where the slicing starts (e.g., where an error was observed).
        target_var: The variable of interest whose influencing statements we want to find.

    Returns:
        List of event dictionaries that form the dynamic backward slice (φ).
        Events are included in the order they were encountered during backward traversal.
    """
    # Index trace by event_id for fast lookup
    trace_indexed = {event['event_id']: event for event in trace}

    # Initialize algorithm state
    δ = {target_var}          # Set of variables whose origins we need to trace
    γ_events = set()          # Set of event_ids whose control dependencies need explaining
    φ = []                    # Result slice: list of event dicts in traversal order

    # Start from start_event_id and go backward to event_id 0
    current_id = start_event_id

    while current_id >= 0:
        stmt = trace_indexed[current_id]

        # Check if we should terminate early
        if len(δ) == 0 and len(γ_events) == 0:
            break

        # --- 1. Dynamic Data Dependency Check ---
        # If this statement defines any variable currently in δ
        vars_defined = set(stmt.get('vars_defined', []))
        if vars_defined & δ:  # Intersection: any defined var is in δ?
            # Remove defined vars from δ
            δ -= vars_defined
            # Add all used vars to δ (to trace their origins)
            vars_used = stmt.get('vars_used', [])
            δ.update(vars_used)
            # Add this stmt to slice φ
            φ.append(stmt)
            # Add this stmt's event_id to γ_events (its control flow may need explaining)
            γ_events.add(current_id)

        # --- 2. Dynamic Control Dependency Check ---
        # Check if this statement is a control decision point for any event in γ_events
        # We look for any event in γ_events that has `-current_id` or `current_id` in its control_dependencies
        controlling = False
        dependent_events_to_remove = set()

        for dep_id in γ_events:
            dep_event = trace_indexed[dep_id]
            ctrl_deps = dep_event.get('control_dependencies', [])
            # Check if this stmt (current_id) controls dep_event (via -current_id or current_id)
            if (-current_id in ctrl_deps) or (current_id in ctrl_deps):
                controlling = True
                dependent_events_to_remove.add(dep_id)

        if controlling:
            # Remove those now-explained events from γ_events
            γ_events -= dependent_events_to_remove
            # Add all used vars of this control stmt to δ (their values influenced the decision)
            vars_used = stmt.get('vars_used', [])
            δ.update(vars_used)
            # Add this stmt to φ and γ_events
            φ.append(stmt)
            γ_events.add(current_id)

        # Move to previous event
        current_id -= 1

    return φ