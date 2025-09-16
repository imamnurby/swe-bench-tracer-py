import sys
import os
import ast
import json
import pprint
from collections import defaultdict
from typing import Dict, Any, List, Tuple
import copy
import re

class ExecutionTracer:
    def __init__(self, output_file: str = "trace.jsonl"):
        self.call_stack = []
        self.call_graph = defaultdict(set)
        self.call_counts = defaultdict(int)
        self.max_depth = 0
        self.trace_data = []
        self.output_file = output_file
        self.source_cache = {}  # Cache for source file contents
        self.event_id = 0
        
        # Stack of variable dictionaries, one per function call
        self.function_variables_stack = []
        
        # Control dependency tracking
        self.control_stack = []  # Stack of (event_id, indentation_level, control_type) for active control statements
        
        # Standard library modules to exclude
        self.stdlib_modules = {
            'abc', '_aix_support', '_android_support', 'annotationlib', 'antigravity', 
            '_apple_support', 'argparse', 'ast', '_ast_unparse', 'asyncio', 'base64', 
            'bdb', 'bisect', 'bz2', 'calendar', 'cmd', 'codecs', 'codeop', 'code', 
            'collections', '_collections_abc', '_colorize', 'colorsys', '_compat_pickle', 
            'compileall', 'compression', 'concurrent', 'configparser', 'contextlib', 
            'contextvars', 'copy', 'copyreg', 'cProfile', 'csv', 'ctypes', 'curses', 
            'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'doctest', 
            'email', 'encodings', 'ensurepip', 'enum', 'filecmp', 'fileinput', 'fnmatch', 
            'fractions', 'ftplib', 'functools', '__future__', 'genericpath', 'getopt', 
            'getpass', 'gettext', 'glob', 'graphlib', 'gzip', 'hashlib', 'heapq', 
            '__hello__', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'importlib', 
            'inspect', 'io', '_ios_support', 'ipaddress', 'json', 'keyword', 'linecache', 
            'locale', 'logging', 'lzma', 'mailbox', '_markupbase', 'mimetypes', 
            'modulefinder', 'multiprocessing', 'netrc', 'ntpath', 'nturl2path', 'numbers', 
            '_opcode_metadata', 'opcode', 'operator', 'optparse', 'os', '_osx_support', 
            'pathlib', 'pdb', '__phello__', 'pickle', 'pickletools', 'pkgutil', 
            'platform', 'plistlib', 'poplib', 'posixpath', 'pprint', 'profile', 
            'profiling', 'pstats', 'pty', '_py_abc', 'pyclbr', 'py_compile', 
            '_pydatetime', '_pydecimal', 'pydoc_data', 'pydoc', '_pyio', '_pylong', 
            '_pyrepl', '_py_warnings', 'queue', 'quopri', 'random', 're', 'reprlib', 
            'rlcompleter', 'runpy', 'sched', 'secrets', 'selectors', 'shelve', 'shlex', 
            'shutil', 'signal', '_sitebuiltins', 'site', 'smtplib', 'socket', 
            'socketserver', 'sqlite3', 'ssl', 'statistics', 'stat', 'string', 
            'stringprep', '_strptime', 'struct', 'subprocess', 'symtable', 'sysconfig', 
            'tabnanny', 'tarfile', 'tempfile', 'test', 'textwrap', 'this', 
            '_threading_local', 'threading', 'timeit', 'tkinter', 'tokenize', 'token', 
            'tomllib', 'traceback', 'tracemalloc', 'trace', 'tree', 'tty', 'turtledemo', 
            'turtle', 'types', 'typing', 'unittest', 'urllib', 'uuid', 'venv', 
            'warnings', 'wave', 'weakref', '_weakrefset', 'webbrowser', 'wsgiref', 
            'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zoneinfo'
        }
        
    def is_stdlib_call(self, filename):
        """Check if the call is from a standard library module"""
        if not filename:
            return False
            
        # Normalize the path
        normalized_path = os.path.normpath(filename)
        path_parts = normalized_path.split(os.sep)
        
        # Check if any part of the path matches stdlib modules
        for part in path_parts:
            if part in self.stdlib_modules:
                return True
                
        # Also check for common stdlib patterns
        if 'site-packages' in normalized_path:
            return False  # Third-party packages
            
        # Check if it's in the standard Python installation
        python_paths = [
            'lib/python',
            'Lib\\',
            '/usr/lib/python',
            '/usr/local/lib/python'
        ]
        
        for py_path in python_paths:
            if py_path in normalized_path:
                return True
                
        return False
        
    def get_source_line(self, filename: str, line_no: int) -> str:
        """Get the source code line from a file"""
        try:
            if filename not in self.source_cache:
                with open(filename, 'r', encoding='utf-8') as f:
                    self.source_cache[filename] = f.readlines()
            
            if 1 <= line_no <= len(self.source_cache[filename]):
                return self.source_cache[filename][line_no - 1].rstrip()
            return ""
        except (IOError, OSError, UnicodeDecodeError):
            return ""
    
    def get_indentation_level(self, source_line: str) -> int:
        """Get the indentation level of a line"""
        return len(source_line) - len(source_line.lstrip())
    
    def is_control_statement(self, source_line: str) -> bool:
        """Check if a line is a control flow statement"""
        stripped = source_line.strip()
        if not stripped.endswith(':'):
            return False
        
        # Check for control flow keywords (excluding try/except/finally/with)
        control_keywords = ['if', 'elif', 'else', 'for', 'while']
        first_word = stripped.split()[0] if stripped.split() else ""
        return first_word in control_keywords
    
    def is_block_continuation(self, source_line: str) -> bool:
        """Check if a line continues a control block (elif, else)"""
        stripped = source_line.strip()
        if not stripped.endswith(':'):
            return False
        
        continuation_keywords = ['elif', 'else']
        first_word = stripped.split()[0] if stripped.split() else ""
        return first_word in continuation_keywords
    
    def get_control_statement_info(self, source_line: str) -> Tuple[bool, str, bool]:
        """
        Analyze a source line to determine control statement information.
        
        Returns:
            Tuple[bool, str, bool]: (is_control, control_type, is_negative_branch)
            - is_control: Whether this line is a control statement
            - control_type: Type of control statement ('if', 'elif', 'else', 'for', 'while', '')
            - is_negative_branch: Whether this represents a negative branch (for elif/else)
        """
        stripped = source_line.strip()
        
        if not stripped.endswith(':'):
            return False, "", False
        
        # Extract the first word
        words = stripped.split()
        if not words:
            return False, "", False
            
        first_word = words[0]
        
        # Check if it's a control statement we care about
        control_keywords = ['if', 'elif', 'else', 'for', 'while']
        if first_word not in control_keywords:
            return False, "", False
        
        # Determine if it's a negative branch
        is_negative_branch = first_word in ['elif', 'else']
        
        return True, first_word, is_negative_branch
    
    def update_control_stack(self, source_line: str, current_indentation: int, current_event_id: int):
        """Update the control stack based on current line"""
        is_control, control_type, is_negative_branch = self.get_control_statement_info(source_line)
        
        # Remove control statements that are no longer active
        # (when we encounter a line with indentation <= control statement's indentation)
        while self.control_stack:
            control_event_id, control_indentation, control_stmt_type = self.control_stack[-1]
            
            # Special case: if current line is a block continuation (elif, else)
            # it should be at the same level as the original if
            if self.is_block_continuation(source_line):
                if current_indentation == control_indentation:
                    # Replace the last control statement with this continuation
                    self.control_stack[-1] = (current_event_id, current_indentation, control_type)
                    break
                elif current_indentation < control_indentation:
                    self.control_stack.pop()
                else:
                    break
            else:
                # Normal case: if current indentation <= control indentation, pop
                if current_indentation <= control_indentation:
                    self.control_stack.pop()
                else:
                    break
        
        # If current line is a control statement, add it to stack
        if is_control and not self.is_block_continuation(source_line):
            self.control_stack.append((current_event_id, current_indentation, control_type))
    
    def get_current_control_dependencies(self, current_control_type: str = "") -> List[int]:
        """
        Get the current control dependencies (event IDs) with negative branch logic.
        
        Args:
            current_control_type: Type of current control statement if any
            
        Returns:
            List[int]: List of event IDs, where negative IDs indicate False branches
        """
        if not self.control_stack:
            return []
        
        dependencies = []
        
        # Handle elif/else negative branch logic
        if current_control_type in ['elif', 'else']:
            # For elif/else, we need to mark previous conditions at the same level as negative
            current_indentation = self.control_stack[-1][1] if self.control_stack else 0
            
            # Find all control statements at the same indentation level (elif chain)
            same_level_controls = []
            other_level_controls = []
            
            for event_id, indentation, control_type in self.control_stack[:-1]:  # Exclude current
                if indentation == current_indentation and control_type in ['if', 'elif']:
                    same_level_controls.append(event_id)
                else:
                    other_level_controls.append(event_id)
            
            # Add other level controls as positive (nested conditions)
            dependencies.extend(other_level_controls)
            
            # Add same level controls as negative (elif chain - previous were False)
            dependencies.extend([-event_id for event_id in same_level_controls])
            
            # Add current control as positive (if it's elif, not else)
            if current_control_type == 'elif' and self.control_stack:
                current_event_id = self.control_stack[-1][0]
                dependencies.append(current_event_id)
            elif current_control_type == 'else':
                # For else, also mark the last elif/if as negative
                if self.control_stack:
                    current_event_id = self.control_stack[-1][0]
                    dependencies.append(-current_event_id)
        else:
            # Normal case: all controls in stack are positive dependencies
            dependencies = [event_id for event_id, _, _ in self.control_stack]
        
        return dependencies
    
    def analyze_variable_usage(self, source_line: str) -> Tuple[List[str], List[str]]:
        """Analyze which variables are defined vs used in a line using AST"""
        vars_defined = set()
        vars_used = set()
        stripped_line = source_line.strip()

        if not stripped_line:
            return [], []

        # Use the existing clever trick for compound statements
        code_to_parse = stripped_line
        if stripped_line.endswith(':'):
            code_to_parse += "\n    pass"

        try:
            tree = ast.parse(code_to_parse, mode='exec')
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Store):
                        # Variable is being assigned to
                        vars_defined.add(node.id)
                    elif isinstance(node.ctx, ast.Load):
                        # Variable is being read from
                        vars_used.add(node.id)
                    # Note: ast.Del context exists but is rare (del statement)
                
                # Handle special cases like for loops where loop variable is defined
                elif isinstance(node, ast.For):
                    # The target of a for loop is considered defined
                    if isinstance(node.target, ast.Name):
                        vars_defined.add(node.target.id)
                    # The iter part uses variables
                    for child in ast.walk(node.iter):
                        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                            vars_used.add(child.id)
                
                # Handle list comprehensions, which can define variables
                elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    for generator in node.generators:
                        if isinstance(generator.target, ast.Name):
                            vars_defined.add(generator.target.id)
                
                # Handle function definitions
                elif isinstance(node, ast.FunctionDef):
                    vars_defined.add(node.name)
                
                # Handle class definitions  
                elif isinstance(node, ast.ClassDef):
                    vars_defined.add(node.name)
                
                # Handle import statements
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        vars_defined.add(name)
                
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        vars_defined.add(name)
                        
        except SyntaxError:
            # If parsing fails, fall back to simple regex approach
            # Look for assignment patterns
            if '=' in stripped_line and not any(op in stripped_line for op in ['==', '!=', '<=', '>=', '<', '>']):
                parts = stripped_line.split('=', 1)
                if len(parts) == 2:
                    # Try to extract variable names from left side
                    left_side = parts[0].strip()
                    # Simple variable name extraction
                    import re
                    var_matches = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', left_side)
                    vars_defined.update(var_matches)
            
            # Extract all identifier-like strings as potentially used variables
            import re
            all_vars = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', stripped_line)
            vars_used.update(all_vars)
        
        return list(vars_defined), list(vars_used)
    
    def serialize_value(self, value: Any) -> Any:
        """Serialize a value for JSON output"""
        try:
            # Try JSON serialization first
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            # Fall back to string representation
            return f"<non-serializable: {type(value).__name__}>"
    
    def get_function_parameters(self, frame) -> Dict[str, Any]:
        """Extract function parameters and their values"""
        code = frame.f_code
        param_names = code.co_varnames[:code.co_argcount]
        params = {}
        
        for name in param_names:
            if name in frame.f_locals:
                params[name] = self.serialize_value(frame.f_locals[name])
        
        # Handle *args and **kwargs
        if code.co_flags & 0x04:  # CO_VARARGS
            varargs_name = code.co_varnames[code.co_argcount]
            if varargs_name in frame.f_locals:
                params['*' + varargs_name] = self.serialize_value(frame.f_locals[varargs_name])
                
        if code.co_flags & 0x08:  # CO_VARKEYWORDS
            kwargs_index = code.co_argcount
            if code.co_flags & 0x04:  # also has *args
                kwargs_index += 1
            kwargs_name = code.co_varnames[kwargs_index]
            if kwargs_name in frame.f_locals:
                params['**' + kwargs_name] = self.serialize_value(frame.f_locals[kwargs_name])
                
        return params
    
    def get_current_function_name(self) -> str:
        """Get the name of the currently executing function"""
        if self.call_stack:
            return self.call_stack[-1]['func_name']
        return "<module>"
        
    def get_function_info(self, frame):
        """Extract detailed function information"""
        func_name = frame.f_code.co_name
        filename = frame.f_code.co_filename
        line_no = frame.f_lineno
        
        # Get just the filename without full path for cleaner output
        short_filename = os.path.basename(filename)
        
        # Get class name if this is a method
        class_name = None
        if 'self' in frame.f_locals:
            class_name = frame.f_locals['self'].__class__.__name__
        elif 'cls' in frame.f_locals:
            class_name = frame.f_locals['cls'].__name__
            
        if class_name:
            qualified_name = f"{short_filename}:{class_name}.{func_name}"
        else:
            qualified_name = f"{short_filename}:{func_name}"
            
        return {
            'qualified_name': qualified_name,
            'filename': filename,
            'short_filename': short_filename,
            'func_name': func_name,
            'class_name': class_name,
            'line_no': line_no
        }
    
    def update_function_variables(self, frame):
        """Update the current function's variable dictionary with local variables"""
        if not self.function_variables_stack:
            return
            
        current_func_vars = self.function_variables_stack[-1]
        
        # Get the function's local variables (excluding globals and builtins)
        code = frame.f_code
        local_var_names = code.co_varnames
        
        # Update only local variables
        for var_name in local_var_names:
            if var_name in frame.f_locals:
                current_func_vars[var_name] = self.serialize_value(frame.f_locals[var_name])
    
    def get_current_seen_variables(self) -> Dict[str, Any]:
        """Get a copy of the current function's seen variables"""
        if self.function_variables_stack:
            return dict(copy.deepcopy(self.function_variables_stack[-1]))
        return {}
    
    def add_trace_entry(self, event_type: str, frame, **kwargs):
        """Add a structured trace entry"""
        filename = frame.f_code.co_filename
        line_no = frame.f_lineno
        function_name = self.get_current_function_name()
        source_line = self.get_source_line(filename, line_no)
        
        entry = {
            'event_id': self.event_id,
            'event_type': event_type,
            'line_number': line_no,
            'statement': source_line,
            # 'filepath': filename,
            'function_name': function_name,
            **kwargs
        }
        self.event_id += 1
        
        self.trace_data.append(entry)
        
    def trace_function(self, frame, event, arg):
        func_info = self.get_function_info(frame)
        
        # Skip standard library calls
        if self.is_stdlib_call(func_info['filename']):
            return self.trace_function
        
        if event == 'call':
            current_depth = len(self.call_stack)
            self.max_depth = max(self.max_depth, current_depth)
            
            # Get function parameters
            parameters = self.get_function_parameters(frame)
            
            # Initialize function variables dictionary with parameters
            func_vars = dict(parameters)
            self.function_variables_stack.append(func_vars)
            
            # Reset control stack for new function
            self.control_stack = []
            
            # Record the relationship for call graph
            if self.call_stack:
                caller_info = self.call_stack[-1]
                caller_name = caller_info['qualified_name']
                callee_name = func_info['qualified_name']
                
                self.call_graph[caller_name].add(callee_name)
                self.call_counts[(caller_name, callee_name)] += 1
            
            self.call_stack.append(func_info)
            
            # Add function entry trace
            self.add_trace_entry(
                'Function', 
                frame, 
                parameters=parameters
            )
            
        elif event == 'return':
            if self.call_stack:
                returned_func = self.call_stack.pop()
                
                # Remove the function's variable dictionary
                if self.function_variables_stack:
                    self.function_variables_stack.pop()
                
                # Reset control stack when exiting function
                self.control_stack = []
                
                # Add return trace
                self.add_trace_entry(
                    'Return',
                    frame,
                    return_value=self.serialize_value(arg)
                )
                
        elif event == 'line':
            # First, update function variables based on current frame state
            self.update_function_variables(frame)
            
            # Get source line and analyze variables
            source_line = self.get_source_line(frame.f_code.co_filename, frame.f_lineno)
            vars_defined, vars_used = self.analyze_variable_usage(source_line)
            
            # Get control statement info for this line
            is_control, control_type, is_negative_branch = self.get_control_statement_info(source_line)
            
            # Update control stack based on current line
            current_indentation = self.get_indentation_level(source_line)
            current_event_id = self.event_id  if not is_negative_branch else -self.event_id
            self.update_control_stack(source_line, current_indentation, current_event_id)
            
            # Get current control dependencies (pass control_type for special elif/else handling)
            control_dependencies = self.get_current_control_dependencies(control_type if is_control else "")
            
            # Get current seen variables
            seen_variables = self.get_current_seen_variables()
            
            # Add line execution trace with enhanced information
            self.add_trace_entry(
                'Line',
                frame,
                vars_defined=vars_defined,
                vars_used=vars_used,
                control_dependencies=control_dependencies,
                seen_variables=seen_variables
            )
                
        elif event == 'exception':
            if self.call_stack:
                exc_type, exc_value, exc_tb = arg
                
                # Add exception trace
                self.add_trace_entry(
                    'Exception',
                    frame,
                    exception_type=exc_type.__name__,
                    exception_value=str(exc_value)
                )
                
        return self.trace_function
    
    def start_tracing(self):
        """Start the trace collection"""
        sys.settrace(self.trace_function)
        
    def stop_tracing(self):
        """Stop the trace collection"""
        sys.settrace(None)
        
    def save_trace(self):
        """Save the collected trace data to JSONL file"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            for entry in self.trace_data:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')
        print(f"Trace saved to {self.output_file}")
        
    def get_trace_summary(self):
        """Get a summary of the collected trace"""
        event_counts = defaultdict(int)
        for entry in self.trace_data:
            event_counts[entry['event_type']] += 1
            
        return {
            'total_events': len(self.trace_data),
            'event_breakdown': dict(event_counts),
            'max_call_depth': self.max_depth,
            'unique_functions': len(self.call_graph),
            'output_file': self.output_file,
            'call_graph': dict(self.call_graph),
            'call_counts': dict(self.call_counts)
        }
                
# ==============================================================================
#  Demonstration Code
# ==============================================================================

def helper_function(value):
    """A simple helper to demonstrate deep calls."""
    prefix = "INFO"
    return f"[{prefix}]: The value is {value}"

def format_output(processed_item):
    """Formats the processed data into a string."""
    item_name, item_length = processed_item
    # Call the helper function
    formatted_string = helper_function(item_length)
    final_output = f"Processed '{item_name}' -> {formatted_string}"
    print(final_output)
    return final_output

def process_item(item, index):
    """Processes a single item from the list."""
    print(f"  Processing item {index}: {item}")
    if (item == "banana"):
        if item != "apple":
            upper_item = item
    else:
        upper_item = item.upper()
    item_len = len(upper_item)
    
    # Pass a tuple to the next function
    processed_data = (upper_item, item_len)
    format_output(processed_data)
    return processed_data

def prepare_data(items):
    """Prepares and iterates over a list of data."""
    print("Preparing data...")
    results = []
    for i, item in enumerate(items):
        result = process_item(item, i)
        results.append(result)
    return results

def main():
    """The main entry point for the demonstration."""
    print("Starting the demonstration.")
    data = ['apple', 'banana', 'cherry']
    processed_results = prepare_data(data)
    print("Demonstration finished.")
    print(f"Final results: {processed_results}")


# ==============================================================================
#  Main Execution Block
# ==============================================================================

def test_simple_if_else(x):
    """Test Case 1: Simple if-else"""
    if x > 5:                    # Event A: condition
        result = "big"           # Event B: control_dependencies=[A] 
    else:                        # (not traced as line event)
        result = "small"         # Event C: control_dependencies=[-A]
    return result

def test_elif_chain(x):
    """Test Case 2: elif chain (same level)"""
    if x < 0:                    # Event A
        result = "negative"      # Event B: control_dependencies=[A]
    elif x == 0:                 # Event C: control_dependencies=[-A, C]
        result = "zero"          # Event D: control_dependencies=[-A, C]
    else:                        # (not traced)
        result = "positive"      # Event E: control_dependencies=[-A, -C]
    return result

def test_nested_if(x, y):
    """Test Case 3: Nested if statements (different levels)"""
    if x > 0:                    # Event A
        if y > 0:                # Event B: control_dependencies=[A]
            result = "both positive"  # Event C: control_dependencies=[A, B]
        else:                    # (not traced)
            result = "x pos, y neg"   # Event D: control_dependencies=[A, -B]
    else:                        # (not traced)
        result = "x negative"    # Event E: control_dependencies=[-A]
    return result

def test_mixed_nested_elif(x, y):
    """Test Case 4: Mixed nested and elif"""
    if x > 10:                   # Event A
        if y > 5:                # Event B: control_dependencies=[A]
            result = "both big"  # Event C: control_dependencies=[A, B]
        else:                    # (not traced)
            result = "x big, y small"  # Event D: control_dependencies=[A, -B]
    elif x > 0:                  # Event E: control_dependencies=[-A, E]
        result = "x medium"      # Event F: control_dependencies=[-A, E]
    else:                        # (not traced)
        result = "x small"       # Event G: control_dependencies=[-A, -E]
    return result

def test_sequential_ifs(x, y):
    """Test Case 5: Sequential independent if statements"""
    result = []
    
    if x > 0:                    # Event A
        result.append("x positive")  # Event B: control_dependencies=[A]
    else:                        # (not traced)
        result.append("x non-positive")  # Event C: control_dependencies=[-A]
    
    if y > 0:                    # Event D: control_dependencies=[] (independent)
        result.append("y positive")  # Event E: control_dependencies=[D]
    else:                        # (not traced)
        result.append("y non-positive")  # Event F: control_dependencies=[-D]
    
    return result

def test_complex_nesting(a, b, c):
    """Test Case 6: Complex nesting with multiple levels"""
    if a > 0:                    # Event A
        if b > 0:                # Event B: control_dependencies=[A]
            if c > 0:            # Event C: control_dependencies=[A, B]
                result = "all positive"      # Event D: control_dependencies=[A, B, C]
            else:                # (not traced)
                result = "a,b pos, c neg"    # Event E: control_dependencies=[A, B, -C]
        elif b == 0:             # Event F: control_dependencies=[A, -B, F]
            result = "a pos, b zero"         # Event G: control_dependencies=[A, -B, F]
        else:                    # (not traced)
            result = "a pos, b neg"          # Event H: control_dependencies=[A, -B, -F]
    else:                        # (not traced)
        result = "a not positive"            # Event I: control_dependencies=[-A]
    return result

if __name__ == "__main__":
    print("--- ExecutionTracer Demonstration ---")
    
    # 1. Initialize the tracer, saving the output to a specific file
    tracer = ExecutionTracer(output_file="demonstration_trace.jsonl")
    
    # 2. Start tracing
    print("\nStarting tracer...")
    tracer.start_tracing()
    
    # 3. Run the target code
    # Using a try/finally block ensures tracing is stopped even if an error occurs
    try:
        # Test Case 1: Simple If-Else
        test_simple_if_else(10)
        test_simple_if_else(3)

        # Test Case 2: elif chain
        test_elif_chain(-5)
        test_elif_chain(0)
        test_elif_chain(5)

        # Test Case 3: Nested if
        test_nested_if(5, 3)
        test_nested_if(5, -3)
        test_nested_if(-5, 3)

        # Test Case 4: Mixed nested and elif
        test_mixed_nested_elif(15, 10)
        test_mixed_nested_elif(15, 2)
        test_mixed_nested_elif(5, 10)
        test_mixed_nested_elif(-5, 10)

        # Test Case 5: Sequential independent ifs
        test_sequential_ifs(5, 3)
        test_sequential_ifs(5, -3)
        test_sequential_ifs(-5, 3)
        test_sequential_ifs(-5, -3)

        # Test Case 6: Complex nesting
        test_complex_nesting(1, 1, 1)
        test_complex_nesting(1, 1, -1)
        test_complex_nesting(1, 0, 1)
        test_complex_nesting(1, -1, 1)
        test_complex_nesting(-1, 1, 1)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # 4. Stop tracing
        print("\nStopping tracer...")
        tracer.stop_tracing()
        
    # 5. Save the collected trace data to the file
    tracer.save_trace()
    
    # 6. Print a summary of the trace to the console
    print("\n--- Trace Summary ---")
    summary = tracer.get_trace_summary()
    pprint.pprint(summary)
    
    print("\n--- Next Steps ---")
    print("Check the 'demonstration_trace.jsonl' file to see the detailed execution trace.")
    print("Each line in the file is a JSON object representing an event (Function call, Line execution, Return).")