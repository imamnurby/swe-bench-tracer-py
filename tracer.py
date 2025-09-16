import sys
import os
import ast
import json
import pprint
from collections import defaultdict
from typing import Dict, Any, List, Tuple
import re
import copy
import io, tokenize


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
        self.control_stack = []
        
        
        # Stack of variable dictionaries, one per function call
        self.function_variables_stack = []
        
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
    
    def _line_indent(self, source_line: str) -> int:
        """Return leading-space indentation level (count of spaces)."""
        # NOTE: keeps it simple (spaces). If you use tabs, adapt accordingly.
        return len(source_line) - len(source_line.lstrip(' '))

    def get_vars_defined_and_used(self, source_line: str) -> Tuple[List[str], List[str]]:
        """Return separate lists of variables defined and used in the statement."""
        defined, used = set(), set()
        stripped = source_line.strip()
        if not stripped:
            return [], []

        code_to_parse = stripped
        if stripped.endswith(':'):
            code_to_parse += "\n    pass"
        try:
            tree = ast.parse(code_to_parse, mode="exec")
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Store):
                        defined.add(node.id)
                    elif isinstance(node.ctx, ast.Load):
                        used.add(node.id)
        except SyntaxError:
            # best-effort only; if parsing fails, return empty lists
            pass
        return list(defined), list(used)

    def _line_indent(self, source_line: str) -> int:
        """Count leading spaces to detect block level."""
        return len(source_line) - len(source_line.lstrip(' '))

    def _is_control_keyword(self, line: str) -> bool:
        """Check if the stripped line starts with a control keyword."""
        keywords = (
            'if', 'elif', 'else', 'for', 'while', 'with',
            'try', 'except', 'finally'
        )
        return line.strip().startswith(keywords)
    
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
    def _strip_comment(self, line: str) -> str:
        """
        Return the line without any trailing comment.
        Uses tokenize to avoid removing # that might be inside strings.
        """
        out = []
        try:
            for tok_type, tok_str, *_ in tokenize.generate_tokens(io.StringIO(line).readline):
                if tok_type == tokenize.COMMENT:
                    break
                out.append(tok_str)
        except tokenize.TokenError:
            return line
        return ''.join(out)

    # AFTER
    def get_vars_involved_in_line(self, source_line: str) -> List[str]:
        """Get all variable names involved in a line using AST"""
        vars_involved = set()
        stripped_line = source_line.strip()

        if not stripped_line:
            return []

        # --- Start of new logic ---
        # Heuristic: If a line ends with a colon, it's likely an incomplete
        # compound statement (if, for, def, etc.). We append 'pass' to make it
        # syntactically valid for ast.parse.
        code_to_parse = stripped_line
        if stripped_line.endswith(':'):
            code_to_parse += "\n    pass"
        # --- End of new logic ---

        try:
            # We now only need to parse in 'exec' mode, as it handles both
            # simple statements and the compound ones we've just fixed.
            tree = ast.parse(code_to_parse, mode='exec')
            
            # Extract all variable names from the AST
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    # We should only care about variables being loaded (used),
                    # not stored (assigned) or deleted, but for simplicity,
                    # we'll still grab all names.
                    vars_involved.add(node.id)
                        
        except SyntaxError:
            # If our heuristic fails and the code is still invalid,
            # we fall back to returning an empty list.
            pass
        
        return list(vars_involved)
    
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
            'filepath': filename,
            'function_name': function_name,
            **kwargs
        }
        self.event_id += 1
        
        self.trace_data.append(entry)
        
    def trace_function(self, frame, event, arg):
        func_info = self.get_function_info(frame)

        if self.is_stdlib_call(func_info['filename']):
            return self.trace_function

        if event == 'call':
            self.control_stack = []  # reset on new function entry
            # --- existing call handling unchanged ---
            current_depth = len(self.call_stack)
            self.max_depth = max(self.max_depth, current_depth)
            parameters = self.get_function_parameters(frame)
            func_vars = dict(parameters)
            self.function_variables_stack.append(func_vars)
            if self.call_stack:
                caller_info = self.call_stack[-1]
                caller_name = caller_info['qualified_name']
                callee_name = func_info['qualified_name']
                self.call_graph[caller_name].add(callee_name)
                self.call_counts[(caller_name, callee_name)] += 1
            self.call_stack.append(func_info)
            self.add_trace_entry('Function', frame, parameters=parameters)

        elif event == 'return':
            self.control_stack = []  # reset when leaving function
            if self.call_stack:
                self.call_stack.pop()
                if self.function_variables_stack:
                    self.function_variables_stack.pop()
                self.add_trace_entry('Return', frame, return_value=self.serialize_value(arg))

        elif event == 'line':
            # Update local variables first (as before)
            self.update_function_variables(frame)
            filename = frame.f_code.co_filename
            line_no = frame.f_lineno
            source_line = self.get_source_line(filename, line_no)

            # Vars defined / used (AST)
            vars_defined, vars_used = self.get_vars_defined_and_used(source_line)

            # Indentation + stripped form
            indent = self._line_indent(source_line)
            stripped = source_line.strip()

            # Hybrid pop rule:
            # - For elif/else/except/finally, we do NOT pop same-level control entries
            #   because they are part of the same conditional chain.
            is_elif_else = stripped.startswith(('elif', 'else', 'except', 'finally'))
            if is_elif_else:
                # pop only strictly deeper blocks (indent < top)
                while self.control_stack and indent < self.control_stack[-1]['indent']:
                    self.control_stack.pop()
            else:
                # normal: pop blocks at same-or-deeper indent (we've left them)
                while self.control_stack and indent <= self.control_stack[-1]['indent']:
                    self.control_stack.pop()

            # Build control dependencies from current control stack:
            # positive id => condition True, negative id => condition False
            control_deps = []
            for entry in self.control_stack:
                eid = entry['id']
                truth = entry.get('truth')
                if truth is True:
                    control_deps.append(eid)
                elif truth is False:
                    control_deps.append(-eid)
                else:
                    # For constructs where we don't/easily evaluate a truth value (e.g. a 'with'),
                    # include the positive id by default.
                    control_deps.append(eid)

            # Decide whether this line starts a control header (if/elif/for/while/with/try/except/finally)
            m = re.match(r'^(if|elif|for|while|with|try|except|finally)\b', stripped)
            if m:
                keyword = m.group(1)
                # Capture current event id (the id that add_trace_entry will assign to this Line)
                current_event_id = self.event_id

                # Evaluate condition truth for condition-bearing constructs where possible
                truth_value = None
                try:
                    if keyword in ('if', 'elif', 'while'):
                        # Extract the expression between keyword and trailing ':'.
                        cond_m = re.match(r'^(?:if|elif|while)\s+(.*):\s*$', stripped)
                        if cond_m:
                            cond_text = cond_m.group(1)
                            # Safe-ish runtime evaluation using the traced frame's context
                            try:
                                cond_eval = eval(compile(cond_text, '<cond>', 'eval'),
                                                frame.f_globals, frame.f_locals)
                                truth_value = bool(cond_eval)
                            except Exception:
                                truth_value = False
                        else:
                            truth_value = False
                    elif keyword == 'for':
                        # Try to evaluate the iterable part after 'in'
                        for_m = re.match(r'^for\s+.*\s+in\s+(.*):\s*$', stripped)
                        if for_m:
                            iterable_text = for_m.group(1)
                            try:
                                iterable_val = eval(compile(iterable_text, '<iter>', 'eval'),
                                                    frame.f_globals, frame.f_locals)
                                # best-effort: check truthiness (note: may mis-handle generators)
                                truth_value = bool(iterable_val)
                            except Exception:
                                truth_value = False
                        else:
                            truth_value = False
                    elif keyword == 'with':
                        # not meaningful as boolean; mark as True (acts as a control boundary)
                        truth_value = True
                    elif keyword in ('try', 'except', 'finally'):
                        # Per spec: treat try/except/finally as normal blocks for slicing
                        truth_value = True
                except Exception:
                    truth_value = False

                # Add the Line event for this control header (the control_deps computed above apply).
                seen_variables = self.get_current_seen_variables()
                self.add_trace_entry(
                    'Line',
                    frame,
                    vars_defined=vars_defined,
                    vars_used=vars_used,
                    control_dependencies=control_deps,
                    seen_variables=seen_variables
                )

                # Push control entry (so body lines inside this header see it).
                # We push the event id that was assigned to this Line (captured earlier).
                self.control_stack.append({
                    'indent': indent,
                    'id': current_event_id,
                    'truth': truth_value
                })

            else:
                # Normal non-control line: just record it with the active control_deps
                seen_variables = self.get_current_seen_variables()
                self.add_trace_entry(
                    'Line',
                    frame,
                    vars_defined=vars_defined,
                    vars_used=vars_used,
                    control_dependencies=control_deps,
                    seen_variables=seen_variables
                )

        elif event == 'exception':
            if self.call_stack:
                exc_type, exc_value, exc_tb = arg
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
            'call_graph': dict(self.call_graph),  # Add this
            'call_counts': dict(self.call_counts)  # And this
        }
        
# # ==============================================================================
# #  Demonstration Code
# # ==============================================================================

# def helper_function(value):
#     """A simple helper to demonstrate deep calls."""
#     prefix = "INFO"
#     return f"[{prefix}]: The value is {value}"

# def format_output(processed_item):
#     """Formats the processed data into a string."""
#     item_name, item_length = processed_item
#     # Call the helper function
#     formatted_string = helper_function(item_length)
#     final_output = f"Processed '{item_name}' -> {formatted_string}"
#     print(final_output)
#     return final_output

# def process_item(item, index):
#     """Processes a single item from the list."""
#     print(f"  Processing item {index}: {item}")
#     if (item == "banana"):
#         if item != "apple":
#             upper_item = item
#     else:
#         upper_item = item.upper()
#     item_len = len(upper_item)
    
#     # Pass a tuple to the next function
#     processed_data = (upper_item, item_len)
#     format_output(processed_data)
#     return processed_data

# def prepare_data(items):
#     """Prepares and iterates over a list of data."""
#     print("Preparing data...")
#     results = []
#     for i, item in enumerate(items):
#         result = process_item(item, i)
#         results.append(result)
#     return results

# def main():
#     """The main entry point for the demonstration."""
#     print("Starting the demonstration.")
#     data = ['apple', 'banana', 'cherry']
#     processed_results = prepare_data(data)
#     print("Demonstration finished.")
#     print(f"Final results: {processed_results}")


# # ==============================================================================
# #  Main Execution Block
# # ==============================================================================

# if __name__ == "__main__":
#     print("--- ExecutionTracer Demonstration ---")
    
#     # 1. Initialize the tracer, saving the output to a specific file
#     tracer = ExecutionTracer(output_file="demonstration_trace.jsonl")
    
#     # 2. Start tracing
#     print("\nStarting tracer...")
#     tracer.start_tracing()
    
#     # 3. Run the target code
#     # Using a try/finally block ensures tracing is stopped even if an error occurs
#     try:
#         main()
#     except Exception as e:
#         print(f"An error occurred: {e}")
#     finally:
#         # 4. Stop tracing
#         print("\nStopping tracer...")
#         tracer.stop_tracing()
        
#     # 5. Save the collected trace data to the file
#     tracer.save_trace()
    
#     # 6. Print a summary of the trace to the console
#     print("\n--- Trace Summary ---")
#     summary = tracer.get_trace_summary()
#     pprint.pprint(summary)
    
#     print("\n--- Next Steps ---")
#     print("Check the 'demonstration_trace.jsonl' file to see the detailed execution trace.")
#     print("Each line in the file is a JSON object representing an event (Function call, Line execution, Return).")
    
    
def test_simple_if_else(x):
    """Test Case 1: Simple if-else"""
    if x > 5:                    
        result = "big"           
    else:                        
        result = "small"         
    return result

def test_elif_chain(x):
    """Test Case 2: elif chain (same level)"""
    if x < 0:                    
        result = "negative"      
    elif x == 0:                 
        result = "zero"          
    else:                        
        result = "positive"     
    return result

def test_nested_if(x, y):
    """Test Case 3: Nested if statements (different levels)"""
    if x > 0:                    
        if y > 0:                
            result = "both positive"  
        else:                    
            result = "x pos, y neg"   
    else:                        
        result = "x negative"    
    return result

def test_mixed_nested_elif(x, y):
    """Test Case 4: Mixed nested and elif"""
    if x > 10:                   
        if y > 5:                
            result = "both big"  
        else:                    
            result = "x big, y small"  
    elif x > 0:                  
        result = "x medium"      
    else:                        
        result = "x small"       
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