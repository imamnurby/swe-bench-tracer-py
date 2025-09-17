import re
from typing import List, Dict, Any, Tuple

def compute_weakest_precondition(
    trace_events: List[Dict],
    target_event_id: int,
    post_condition_vars: Dict[str, Any]
) -> Tuple[str, List[Tuple[int, str]]]:
    """
    Computes weakest precondition by backward symbolic execution along trace.

    Args:
        trace_events: list of trace event dicts.
        target_event_id: event ID where post-condition should hold.
        post_condition_vars: dict like {'y': 100} → will form "y == 100"

    Returns:
        wp_formula: str — final weakest precondition
        contribution_map: List[(line_number, statement)] — statements that contributed
    """
    # Initialize Q from post_condition_vars
    conditions = []
    for var, val in post_condition_vars.items():
        val_str = repr(val) if isinstance(val, str) else str(val)
        conditions.append(f"{var} == {val_str}")
    Q = " ∧ ".join(conditions) if conditions else "true"
    
    contribution_map = []

    # Build event_id -> event map
    event_map = {event['event_id']: event for event in trace_events}

    current_id = target_event_id

    while current_id >= 0:
        if current_id not in event_map:
            current_id -= 1
            continue

        event = event_map[current_id]
        event_type = event.get('event_type')

        # --- Handle "Line" events ---
        if event_type == "Line":
            stmt = event['statement'].strip()
            line_num = event['line_number']

            # Rule 1: Assignment
            assign_match = re.match(r'^(\w+)\s*=\s*(.+)$', stmt)
            if assign_match:
                var_name = assign_match.group(1)
                expr = assign_match.group(2).strip()

                # Remove trailing comments from expression (if any)
                expr = re.split(r'\s*#', expr)[0].strip()

                # Only wrap in parentheses if expression contains operators
                if any(op in expr for op in '+-*/%<>=!&|'):
                    safe_expr = f"({expr})"
                else:
                    safe_expr = expr

                # Substitute using word boundary to avoid partial matches
                pattern = r'\b' + re.escape(var_name) + r'\b'
                Q = re.sub(pattern, safe_expr, Q)
                contribution_map.append((line_num, stmt))

            # Rule 2: Branch condition (if/elif)
            elif stmt.startswith('if ') or stmt.startswith('elif '):
                # Extract condition: remove 'if ', strip trailing ':', remove comment
                condition = stmt[3:].rstrip(':').strip()
                # Remove inline comments
                condition = re.split(r'\s*#', condition)[0].strip()

                if Q == "true":
                    Q = condition
                else:
                    Q = f"({condition}) ∧ ({Q})"
                contribution_map.append((line_num, stmt))

        # --- Handle "Function" events ---
        elif event_type == "Function":
            param_sources = event.get('parameter_sources', {})
            for param, sources in param_sources.items():
                if not sources:
                    continue
                source_var = sources[0].get('var')
                if not source_var:
                    continue
                pattern = r'\b' + re.escape(param) + r'\b'
                if re.search(pattern, Q):
                    Q = re.sub(pattern, source_var, Q)
                    contribution_map.append((event['line_number'], event['statement']))

        current_id -= 1

    return Q, contribution_map


if __name__ == "__main__":
    # Buggy trace: x = 50 → y = 150 expected at D(y)
    trace_buggy = [
        {'event_id': 10, 'event_type': 'Function', 'line_number': 769, 'statement': 'def D(y):', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:D', 'caller_name': 'tracer.py:C', 'parameters': {'y': 150}, 'parameter_sources': {'y': [{'var': 'z', 'event_id': 4}]}, 'inherited_control_dependencies': [-8]},
        {'event_id': 8, 'event_type': 'Line', 'line_number': 764, 'statement': '    if B == 150:', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:C', 'vars_defined': [], 'vars_used': ['B'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'z': 150}},
        {'event_id': 4, 'event_type': 'Line', 'line_number': 763, 'statement': '    z = B(z)', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:C', 'vars_defined': ['z'], 'vars_used': ['B', 'z'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'z': 50}},
        {'event_id': 3, 'event_type': 'Function', 'line_number': 762, 'statement': 'def C(z):', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:C', 'caller_name': 'tracer.py:A', 'parameters': {'z': 50}, 'parameter_sources': {'z': [{'var': 'x', 'event_id': 1}]}, 'inherited_control_dependencies': []},
        {'event_id': 1, 'event_type': 'Line', 'line_number': 756, 'statement': '    x = 50', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:A', 'vars_defined': ['x'], 'vars_used': [], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {}}
# {'event_id': 24, 'event_type': 'Line', 'line_number': 811, 'statement': '                total += transform_even(val)', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['total'], 'vars_used': ['transform_even', 'val'], 'control_dependencies': [20, 22, 23], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 105, 'items': [10, 11, 12], 'i': 2, 'val': 12}},
# {'event_id': 23, 'event_type': 'Line', 'line_number': 810, 'statement': '            if val % 2 == 0:', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': [], 'vars_used': ['val'], 'control_dependencies': [20, 22], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 105, 'items': [10, 11, 12], 'i': 2, 'val': 12}},
# {'event_id': 22, 'event_type': 'Line', 'line_number': 809, 'statement': '        if i > 0:            # 🐞 BUG: should be `if val > 0`', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': [], 'vars_used': ['i'], 'control_dependencies': [20], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 105, 'items': [10, 11, 12], 'i': 2, 'val': 12}},
# {'event_id': 21, 'event_type': 'Line', 'line_number': 808, 'statement': '        val = items[i]', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['val'], 'vars_used': ['i', 'items'], 'control_dependencies': [20], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 105, 'items': [10, 11, 12], 'i': 2, 'val': 11}},
# {'event_id': 20, 'event_type': 'Line', 'line_number': 807, 'statement': '    for i in range(len(items)):', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['i'], 'vars_used': ['range', 'len', 'items'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 105, 'items': [10, 11, 12], 'i': 1, 'val': 11}},
# {'event_id': 20, 'event_type': 'Line', 'line_number': 807, 'statement': '    for i in range(len(items)):', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['i'], 'vars_used': ['range', 'len', 'items'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 105, 'items': [10, 11, 12], 'i': 1, 'val': 11}},
# {'event_id': 5, 'event_type': 'Line', 'line_number': 806, 'statement': '    items = get_items(n)', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['items'], 'vars_used': ['get_items', 'n'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 0}},
# {'event_id': 3, 'event_type': 'Function', 'line_number': 804, 'statement': 'def process_list(n):', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'caller_name': 'tracer.py:main', 'parameters': {'n': 10}, 'parameter_sources': {'n': [{'var': 'a', 'event_id': 1}]}, 'inherited_control_dependencies': []},
# {'event_id': 1, 'event_type': 'Line', 'line_number': 800, 'statement': '    a = 10', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:main', 'vars_defined': ['a'], 'vars_used': [], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {}}    
]

    # Golden trace: x = 0 → y = 100 expected at D(y)
    trace_golden = [
        {'event_id': 10, 'event_type': 'Function', 'line_number': 769, 'statement': 'def D(y):', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:D', 'caller_name': 'tracer.py:C', 'parameters': {'y': 100}, 'parameter_sources': {'y': [{'var': 'z', 'event_id': 4}]}, 'inherited_control_dependencies': [-8]},
        {'event_id': 8, 'event_type': 'Line', 'line_number': 764, 'statement': '    if B == 150:', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:C', 'vars_defined': [], 'vars_used': ['B'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'z': 100}},
        {'event_id': 4, 'event_type': 'Line', 'line_number': 763, 'statement': '    z = B(z)', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:C', 'vars_defined': ['z'], 'vars_used': ['B', 'z'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'z': 0}},
        {'event_id': 3, 'event_type': 'Function', 'line_number': 762, 'statement': 'def C(z):', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:C', 'caller_name': 'tracer.py:A', 'parameters': {'z': 0}, 'parameter_sources': {'z': [{'var': 'x', 'event_id': 1}]}, 'inherited_control_dependencies': []},
        {'event_id': 1, 'event_type': 'Line', 'line_number': 756, 'statement': '    x = 0', 'filepath': '/home/yusuf/...', 'function_name': 'tracer.py:A', 'vars_defined': ['x'], 'vars_used': [], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {}},
#     {'event_id': 29, 'event_type': 'Line', 'line_number': 785, 'statement': '                total += transform_even(val)', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['total'], 'vars_used': ['val', 'transform_even'], 'control_dependencies': [25, 27, 28], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 205, 'items': [10, 11, 12], 'i': 2, 'val': 12}},
# {'event_id': 28, 'event_type': 'Line', 'line_number': 784, 'statement': '            if val % 2 == 0:', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': [], 'vars_used': ['val'], 'control_dependencies': [25, 27], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 205, 'items': [10, 11, 12], 'i': 2, 'val': 12}},
# {'event_id': 27, 'event_type': 'Line', 'line_number': 783, 'statement': '        if val > 0:', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': [], 'vars_used': ['val'], 'control_dependencies': [25], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 205, 'items': [10, 11, 12], 'i': 2, 'val': 12}},
# {'event_id': 26, 'event_type': 'Line', 'line_number': 782, 'statement': '        val = items[i]', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['val'], 'vars_used': ['items', 'i'], 'control_dependencies': [25], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 205, 'items': [10, 11, 12], 'i': 2, 'val': 11}},
# {'event_id': 25, 'event_type': 'Line', 'line_number': 781, 'statement': '    for i in range(len(items)):', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['i'], 'vars_used': ['range', 'items', 'len'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 205, 'items': [10, 11, 12], 'i': 1, 'val': 11}},
# {'event_id': 25, 'event_type': 'Line', 'line_number': 781, 'statement': '    for i in range(len(items)):', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['i'], 'vars_used': ['range', 'items', 'len'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 205, 'items': [10, 11, 12], 'i': 1, 'val': 11}},
# {'event_id': 5, 'event_type': 'Line', 'line_number': 780, 'statement': '    items = get_items(n)  # returns [n, n+1, n+2]', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'vars_defined': ['items'], 'vars_used': ['get_items', 'n'], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {'n': 10, 'total': 0}},
# {'event_id': 3, 'event_type': 'Function', 'line_number': 778, 'statement': 'def process_list(n):', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:process_list', 'caller_name': 'tracer.py:main', 'parameters': {'n': 10}, 'parameter_sources': {'n': [{'var': 'a', 'event_id': 1}]}, 'inherited_control_dependencies': []},
# {'event_id': 1, 'event_type': 'Line', 'line_number': 774, 'statement': '    a = 10', 'filepath': '/home/yusuf/ds-symbolic-explanation/swe-bench-tracer-py/tracer.py', 'function_name': 'tracer.py:main', 'vars_defined': ['a'], 'vars_used': [], 'control_dependencies': [], 'inherited_control_dependencies': [], 'seen_variables': {}},
    ]

    print("=== BUGGY TRACE ===")
    # wp_buggy, contribs_buggy = compute_weakest_precondition(trace_buggy, 24, {'total': 105})
    wp_buggy, contribs_buggy = compute_weakest_precondition(trace_buggy, 10, {'y': 150})

    print("Weakest Precondition:", wp_buggy)
    print("Contributions:")
    for line, stmt in contribs_buggy:
        print(f"  Line {line}: {stmt}")

    print("\n=== GOLDEN TRACE ===")
    wp_golden, contribs_golden = compute_weakest_precondition(trace_golden, 10, {'y': 100})
    print("Weakest Precondition:", wp_golden)
    print("Contributions:")
    for line, stmt in contribs_golden:
        print(f"  Line {line}: {stmt}")

    print("\n=== DIFFERENTIAL ANALYSIS ===")
    print("Buggy WP   :", wp_buggy)
    print("Golden WP  :", wp_golden)
    if wp_buggy == wp_golden:
        print("→ NO DIFFERENCE DETECTED")
    else:
        print("→ DIFFERENCE DETECTED: likely root cause of bug")