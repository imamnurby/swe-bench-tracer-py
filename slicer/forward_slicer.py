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

def map_call_sites_to_func_events(trace: List[Dict]) -> Dict[int, Dict]:
    """
    Creates a mapping from a call site event ID to its corresponding 'Function' entry event.

    This is essential for forward slicing to trace data dependencies from arguments
    at a call site to the parameters within the called function.

    It assumes the line event that performs the call occurs immediately before
    the corresponding 'Function' entry event in the trace.

    Args:
        trace: The full execution trace.

    Returns:
        A dictionary where keys are the event_id of a 'Line' event that calls a function,
        and values are the corresponding 'Function' entry event dictionary.
    """
    call_site_to_func_map = {}
    for i, event in enumerate(trace):
        if event['event_type'] == 'Function' and i > 0:
            # The line event making the call is assumed to be right before the function entry event
            call_site_event = trace[i-1]
            if call_site_event['event_type'] == 'Line':
                 call_site_to_func_map[call_site_event['event_id']] = event
    
    return call_site_to_func_map

def map_return_events_to_call_sites(trace_indexed: Dict[int, Dict], call_site_to_return_map: Dict[int, Dict]) -> Dict[int, Dict]:
    """
    Creates a mapping from a 'Return' event ID to its corresponding call site 'Line' event.

    This is the inverse of map_call_sites_to_return_events and is useful for
    forward slicing to trace a returned value back to the variable it is assigned to.

    Args:
        trace_indexed: A dictionary mapping event_id to the event dictionary.
        call_site_to_return_map: The map from call site ID to the return event.

    Returns:
        A dictionary where keys are the event_id of a 'Return' event, and values
        are the corresponding 'Line' event dictionary for the call site.
    """
    return_to_call_site_map = {}
    for call_site_id, return_event in call_site_to_return_map.items():
        # The value in the original map is the return event dictionary.
        # We use its event_id as the key in our new inverted map.
        # The value is the call site event dictionary, which we look up.
        return_to_call_site_map[return_event['event_id']] = trace_indexed[call_site_id]
        
    return return_to_call_site_map

def forward_slice(trace: List[Dict], start_event_id: int, target_vars: List[str]) -> List[Dict]:
    """
    Performs forward dynamic slicing on an execution trace using a multi-pass approach
    to correctly handle interprocedural data dependencies.

    Args:
        trace: List of event dictionaries from execution trace.
        start_event_id: The event ID where the slicing starts.
        target_vars: The initial list of variables whose influence will be tracked.

    Returns:
        List of event dictionaries that form the dynamic forward slice, ordered
        chronologically.
    """
    try:
        trace_indexed = {event['event_id']: event for event in trace}
        call_site_to_return_map = map_call_sites_to_return_events(trace)
        call_site_to_func_map = map_call_sites_to_func_events(trace)
        return_to_call_site_map = map_return_events_to_call_sites(trace_indexed, call_site_to_return_map)
        
        scope_map = build_scope_map(trace)

        # The initial variables of interest belong to the scope of the start event.
        start_scope_id = scope_map.get(start_event_id)
        if start_scope_id is None:
            start_scope_id = -1 # Use -1 to denote the global scope
        
        # Convert initial target_vars to scoped variables
        cumulative_affected_vars = {(var, start_scope_id) for var in target_vars}

        slice_event_ids = {start_event_id} # The start event is always in the slice
        
        # --- Multi-Pass Slicing Loop ---
        # This loop continues until a full backward pass finds no new affected variables.
        while True:
            pass_affected_vars = cumulative_affected_vars.copy()
            newly_affected_vars = set()
            
            # Events added to the slice in this pass become sources of control dependency.
            pass_control_sources = {start_event_id}

            # --- Single Forward Pass ---
            for current_id in range(start_event_id, len(trace)):
                stmt = trace_indexed[current_id]

                if stmt['event_type'] == 'Exception':
                    continue
                
                is_data_dependent = False
                is_control_dependent = False
                current_scope_id = scope_map.get(current_id, -1)

                # 1. Dynamic Data Dependency Check
                vars_used = set(stmt.get('vars_used', []))
                scoped_vars_used = {(var, current_scope_id) for var in vars_used}
                if scoped_vars_used & pass_affected_vars:
                    is_data_dependent = True

                # 2. Dynamic Control Dependency Check
                # Check if this event is controlled by an event already added in this pass.
                all_ctrl_deps = set(stmt.get('control_dependencies', [])) | \
                            set(stmt.get('inherited_control_dependencies', []))
                if any(abs(c_id) in pass_control_sources for c_id in all_ctrl_deps):
                    is_control_dependent = True
                
                # Add statement to slice if it's affected by data or control flow
                if is_data_dependent or is_control_dependent or current_id == start_event_id:
                    slice_event_ids.add(current_id)
                    pass_control_sources.add(current_id) # It can now control subsequent events in this pass.

                    # The variables *defined* by this statement are now considered affected
                    vars_defined = stmt.get('vars_defined', [])
                    scoped_vars_defined = {(var, current_scope_id) for var in vars_defined}
                    pass_affected_vars.update(scoped_vars_defined)
                    newly_affected_vars.update(scoped_vars_defined)

                    # --- Interprocedural Data Dependency Propagation (Forward) ---
                    if current_id in call_site_to_func_map:
                        func_event = call_site_to_func_map[current_id]
                        func_scope_id = func_event['event_id']
                        call_args = stmt.get('vars_used', [])
                        func_params = func_event.get('params', [])
                        for arg, param in zip(call_args, func_params):
                            if (arg, current_scope_id) in pass_affected_vars:
                                scoped_param = (param, func_scope_id)
                                if scoped_param not in pass_affected_vars:
                                    pass_affected_vars.add(scoped_param)
                                    newly_affected_vars.add(scoped_param)

                    if stmt['event_type'] == 'Return' and current_id in return_to_call_site_map:
                        call_site_event = return_to_call_site_map[current_id]
                        call_site_scope_id = scope_map.get(call_site_event['event_id'], -1)
                        returned_vars = stmt.get('vars_used', [])
                        if returned_vars and (returned_vars[0], current_scope_id) in pass_affected_vars:
                            assigned_vars = call_site_event.get('vars_defined', [])
                            if assigned_vars:
                                scoped_assigned_var = (assigned_vars[0], call_site_scope_id)
                                if scoped_assigned_var not in pass_affected_vars:
                                    pass_affected_vars.add(scoped_assigned_var)
                                    newly_affected_vars.add(scoped_assigned_var)
                                            
            # --- Check for Convergence ---
            # If this pass did not discover any new affected variables, we are done.
            if not (newly_affected_vars - cumulative_affected_vars):
                break
            
            # Otherwise, update the cumulative set and run another pass.
            cumulative_affected_vars.update(newly_affected_vars)
    except:
        print(stmt)    
    # --- Finalize Slice ---
    # Retrieve the full event dictionaries for the IDs in the slice.
    # Sort them in reverse chronological order to match the backward traversal.
    slice_result = [trace_indexed[id] for id in sorted(list(slice_event_ids))]
    
    return slice_result