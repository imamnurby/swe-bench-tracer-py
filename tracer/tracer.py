import sys
import os
import ast
import json
from collections import defaultdict
from typing import Dict, Any, List, Tuple
import re
import copy
import io, tokenize
import inspect

from pathlib import Path
from tracer.util import get_func_qualname

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
        self.inherited_control_stack = []
        self.control_stack_stack = []  # Stack for managing control_stack across calls
        
        # Map: qualified_function_name -> { var_name -> last_def_event_id }
        # This is used to track where variables were last defined (per-function)
        self.last_def_event = defaultdict(dict)
        
        # Keep track of the most recent Line event per frame so we can
        # fill in seen_variables AFTER the line executes.
        self._pending_line_events = {}
        
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
        
    def __enter__(self):
        self.start_tracing()
        return self
    
    def __exit__(self, exc_type, exc_value, tb):
        self.stop_tracing()
        self.save_trace()
        # suppress exception propagation
        return True
    
    def _get_vars_defined_and_used(self, source_line: str) -> Tuple[List[str], List[str]]:
        """Return separate lists of variables defined and used in the statement."""
        defined, used = set(), set()
        if not source_line or not source_line.strip():
            return [], []

        # Remove comments safely so colon-trick and AST parsing work
        code_no_comments = self._strip_comments_preserving_strings(source_line).rstrip()
        # Keep a final fallback to the original stripped form
        stripped = code_no_comments.strip()
        if not stripped:
            return [], []

        code_to_parse = stripped
        # If the logical code (without comments) ends with a colon, make it parseable
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
            # best-effort only
            pass

        return list(defined), list(used)

    def _line_indent(self, source_line: str) -> int:
        """Count leading spaces to detect block level."""
        return len(source_line) - len(source_line.lstrip(' '))

    def _is_control_keyword(self, line: str) -> bool:
        """Check if the stripped line starts with a control keyword."""
        keywords = (
            'if', 'elif', 'else', 'for', 'while'
        )
        return line.strip().startswith(keywords)
    
    def _is_stdlib_call(self, filename):
        """Check if the call is from a standard library module"""
        if not filename:
            return False

        if filename.startswith('<frozen'):
            return True
        
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
        
    def _get_source_line(self, filename: str, line_no: int) -> str:
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
        
    def _strip_comments_preserving_strings(self, line: str) -> str:
        """
        Remove inline comments from a single source line while preserving
        '#' inside string literals. Uses tokenize to avoid breaking strings.
        Returns a best-effort comment-free source line.
        """
        try:
            tokens = []
            # generate_tokens yields namedtuple with .type and .string in Python 3
            for tok in tokenize.generate_tokens(io.StringIO(line).readline):
                # Skip comment tokens
                if tok.type == tokenize.COMMENT:
                    continue
                tokens.append((tok.type, tok.string))
            # Reconstruct source without comment tokens
            return tokenize.untokenize(tokens)
        except Exception:
            # Fallback: naive split but only if tokenize failed
            return line.split('#', 1)[0]

    def _get_call_arg_varnames_from_call_line(self, source_line: str, callee_func_name: str):
        """
        Parse a single source line and, if it contains a call to `callee_func_name`,
        return a tuple (positional_arg_varlists, keyword_arg_varmap).

        - positional_arg_varlists: list where each element is a list of variable
          names used in the corresponding positional argument expression.
        - keyword_arg_varmap: dict mapping keyword-name -> list(variable-names).
          If a `**kwargs` expansion is present it will be returned under the
          special key '__KW_EXPANSION__'.

        Best-effort: returns ([], {}) on parse errors or no match.
        """
        code_no_comments = self._strip_comments_preserving_strings(source_line)
        try:
            tree = ast.parse(code_no_comments, mode='exec')
        except SyntaxError:
            return [], {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                match = False
                if isinstance(func, ast.Name) and func.id == callee_func_name:
                    match = True
                elif isinstance(func, ast.Attribute) and func.attr == callee_func_name:
                    match = True

                if not match:
                    continue

                pos_arg_varlists = []
                for arg in node.args:
                    sub = arg.value if isinstance(arg, ast.Starred) else arg
                    varnames = set()
                    for n in ast.walk(sub):
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                            varnames.add(n.id)
                    pos_arg_varlists.append(list(varnames))

                kw_arg_map = {}
                for kw in node.keywords:
                    key = kw.arg  # None indicates a **kwargs expansion
                    val = kw.value
                    varnames = set()
                    for n in ast.walk(val):
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                            varnames.add(n.id)
                    if key is None:
                        kw_arg_map['__KW_EXPANSION__'] = list(varnames)
                    else:
                        kw_arg_map[key] = list(varnames)

                return pos_arg_varlists, kw_arg_map

        return [], {}


    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for JSON output"""
        try:
            # Try JSON serialization first
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            # Fall back to string representation
            return f"<non-serializable: {type(value).__name__}>"
    
    def _get_function_parameters(self, frame) -> Dict[str, Any]:
        """Extract function parameters and their values"""
        code = frame.f_code
        param_names = code.co_varnames[:code.co_argcount]
        params = {}
        
        for name in param_names:
            if name in frame.f_locals:
                params[name] = self._serialize_value(frame.f_locals[name])
        
        # Handle *args and **kwargs
        if code.co_flags & 0x04:  # CO_VARARGS
            varargs_name = code.co_varnames[code.co_argcount]
            if varargs_name in frame.f_locals:
                params['*' + varargs_name] = self._serialize_value(frame.f_locals[varargs_name])
                
        if code.co_flags & 0x08:  # CO_VARKEYWORDS
            kwargs_index = code.co_argcount
            if code.co_flags & 0x04:  # also has *args
                kwargs_index += 1
            kwargs_name = code.co_varnames[kwargs_index]
            if kwargs_name in frame.f_locals:
                params['**' + kwargs_name] = self._serialize_value(frame.f_locals[kwargs_name])
                
        return params
    
    def _get_current_function_name(self) -> str:
        """Get the name of the currently executing function"""
        if self.call_stack:
            return self.call_stack[-1]['qualified_name']
        return "<module>"
        
    def _get_function_info(self, frame):
        """Extract detailed function information"""
        func_name = frame.f_code.co_name
        func_qualname = get_func_qualname(frame)
        filename = frame.f_code.co_filename
        line_no = frame.f_lineno
        module = inspect.getmodule(frame)        

        if module is None:
            mod_name = Path(filename).stem
        else:
            mod_name = module.__name__
            if mod_name == "__main__":
                module_file = getattr(module, "__file__", None)
                if module_file:
                    mod_name = Path(module_file).stem
                else:
                    mod_name = Path(filename).stem
        
        return {
            'qualified_name': f'{mod_name}:{func_qualname}',
            'filename': filename,
            'func_name': func_name,
            'mod_name': mod_name,
            'line_no': line_no
        }
    
    def _update_function_variables(self, frame):
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
                current_func_vars[var_name] = self._serialize_value(frame.f_locals[var_name])
    
    def _get_current_seen_variables(self) -> Dict[str, Any]:
        """Get a copy of the current function's seen variables"""
        if self.function_variables_stack:
            return dict(copy.deepcopy(self.function_variables_stack[-1]))
        return {}
    
    def _add_trace_entry(self, event_type: str, frame, **kwargs):
        """Add a structured trace entry"""
        filename = frame.f_code.co_filename
        line_no = frame.f_lineno
        function_name = self._get_current_function_name()
        source_line = self._get_source_line(filename, line_no)
        
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
        
    def _trace_function(self, frame, event, arg):
        if event == 'call' and frame.f_locals.get('self') is self:
            return None
        
        func_info = self._get_function_info(frame)

        if self._is_stdlib_call(func_info['filename']):
            return self._trace_function

        if event == 'call':
            caller_snapshot = []
            # include caller's local controls
            caller_snapshot.extend([dict(e) for e in self.control_stack])
            # include everything caller already inherited
            if self.inherited_control_stack:
                caller_snapshot.extend([dict(e) for e in self.inherited_control_stack[-1]])
            self.inherited_control_stack.append(caller_snapshot)
            self.control_stack_stack.append(self.control_stack) # Save the caller's stack
            self.control_stack = []  # reset on new function entry

            # --- existing call handling unchanged (depth / vars stack) ---
            current_depth = len(self.call_stack)
            self.max_depth = max(self.max_depth, current_depth)

            # serialize parameters for JSON output (existing helper)
            parameters = self._get_function_parameters(frame)
            func_vars = dict(parameters)
            self.function_variables_stack.append(func_vars)

                        # --- NEW: compute parameter_sources (best-effort)
            # Strategy:
            # 1) Parse the caller source line to find the call AST and extract variables
            #    used in each argument expression (positional and keyword).
            # 2) Map those variable names to their last-definition event id recorded
            #    for the caller-qualified scope.
            # 3) If no variables are found (e.g. literal-only arg or parse failed),
            #    fall back to the previous identity/equality heuristic.
            parameter_sources = {}
            # caller frame is the previous stack frame (may be None for some calls)
            caller_frame = frame.f_back
            caller_qualified = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"

            # Raw parameter names from callee code object (handle basic args only; extend if needed)
            code = frame.f_code
            param_count = code.co_argcount
            param_names = list(code.co_varnames[:param_count])

            # handle positional varargs and kwargs names if present
            idx = param_count
            varargs_name = None
            kwargs_name = None
            if code.co_flags & 0x04:  # CO_VARARGS
                varargs_name = code.co_varnames[idx]
                param_names.append(varargs_name)
                idx += 1
            if code.co_flags & 0x08:  # CO_VARKEYWORDS
                kwargs_name = code.co_varnames[idx]
                param_names.append(kwargs_name)

            # Attempt to parse the caller's source line and extract variable names used
            pos_arg_vars, kw_arg_vars = [], {}
            try:
                if caller_frame is not None:
                    caller_src = self._get_source_line(caller_frame.f_code.co_filename, caller_frame.f_lineno)
                    pos_arg_vars, kw_arg_vars = self._get_call_arg_varnames_from_call_line(caller_src, func_info['func_name'])
            except Exception:
                pos_arg_vars, kw_arg_vars = [], {}

            # Map parameters -> list of variable names that appear in the corresponding arg expression
            fixed_count = param_count
            for i, pname in enumerate(param_names):
                found_varnames = []

                # 1) If the argument was passed as a keyword (e.g. B(k=x+1)), use that mapping
                if pname in kw_arg_vars:
                    found_varnames = kw_arg_vars.get(pname, []) or []
                # 2) Positional mapping for fixed parameters
                elif i < fixed_count:
                    if i < len(pos_arg_vars):
                        found_varnames = pos_arg_vars[i] or []
                # 3) varargs: collect any remaining positional args beyond the fixed arity
                elif varargs_name is not None and pname == varargs_name:
                    extra = pos_arg_vars[fixed_count:] if len(pos_arg_vars) > fixed_count else []
                    agg = []
                    for sub in extra:
                        agg.extend(sub)
                    found_varnames = agg
                # 4) kwargs expansion (**kwargs) — best-effort: include any kw expansion varnames
                elif kwargs_name is not None and pname == kwargs_name:
                    found_varnames = kw_arg_vars.get('__KW_EXPANSION__', []) or []

                # 5) Fallback to identity/equality heuristic if we didn't find any variable names
                if not found_varnames and caller_frame is not None:
                    raw_val = frame.f_locals.get(pname, None)
                    found_names = []
                    for cname, cval in caller_frame.f_locals.items():
                        try:
                            if raw_val is cval:
                                found_names.append(cname)
                            elif raw_val == cval:
                                found_names.append(cname)
                        except Exception:
                            # ignore comparison errors
                            pass
                    # deduplicate while preserving ordering
                    found_varnames = list(dict.fromkeys(found_names))

                # 6) Convert variable names -> {var, event_id} objects, or None if empty
                if found_varnames:
                    mapped = []
                    for vname in found_varnames:
                        src_event = self.last_def_event.get(caller_qualified, {}).get(vname)
                        mapped.append({"var": vname, "event_id": src_event})
                    parameter_sources[pname] = mapped
                else:
                    parameter_sources[pname] = None

            # update call graph info (existing)
            if self.call_stack:
                caller_info = self.call_stack[-1]
                caller_name = caller_info['qualified_name']
                callee_name = func_info['qualified_name']
                self.call_graph[caller_name].add(callee_name)
                self.call_counts[(caller_name, callee_name)] += 1

            # push callee onto the call stack (existing)
            self.call_stack.append(func_info)

            # add the Function entry — include parameter_sources
            self._add_trace_entry(
                'Function',
                frame,
                function_name=func_info['qualified_name'],  # ← callee (correct scope)
                caller_name=self.call_stack[-2]['qualified_name'] if len(self.call_stack) > 1 else "<module>",  # ← new field
                parameters=parameters,
                parameter_sources=parameter_sources,
                inherited_control_dependencies=[
                    e['id'] if e.get('truth') is not False else -e['id']
                    for e in caller_snapshot
                ]
            )

            # Record that the callee's parameters are "defined" by the Function event we just emitted.
            # Use the Function event's id = self.event_id - 1
            callee_qualified = func_info['qualified_name']
            for pname in param_names:
                # note: we record only the parameter name (they are locals of the callee)
                self.last_def_event[callee_qualified][pname] = self.event_id - 1

        elif event == 'return':
            if self.control_stack_stack:
                self.control_stack = self.control_stack_stack.pop() # Restore caller's stack
            else:
                self.control_stack = [] # Fallback for safety
            # Capture callee name BEFORE popping
            returning_func_name = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"
            caller_name_after_return = self.call_stack[-2]['qualified_name'] if len(self.call_stack) > 1 else "<module>" if len(self.call_stack) == 1 else None

            if self.call_stack:
                self.call_stack.pop()
                
                # Finalize any last line still pending for this frame
                if frame in self._pending_line_events:
                    prev_event = self._pending_line_events.pop(frame)
                    prev_event['seen_variables'] = self._serialize_value(dict(frame.f_locals))
                
                if self.function_variables_stack:
                    self.function_variables_stack.pop()
                if self.inherited_control_stack:
                    self.inherited_control_stack.pop()
                self._add_trace_entry(
                    'Return',
                    frame,
                    function_name=returning_func_name,   # ← callee (the one returning)
                    caller_name=caller_name_after_return, # ← who we return to
                    return_value=self._serialize_value(arg)
                )

        elif event == 'line':
            if frame in self._pending_line_events:
                prev_event = self._pending_line_events.pop(frame)
                # capture the now-up-to-date locals
                prev_event['seen_variables'] = self._serialize_value(dict(frame.f_locals))
                
            # Update local variables first (as before)
            self._update_function_variables(frame)
            filename = frame.f_code.co_filename
            line_no = frame.f_lineno
            source_line = self._get_source_line(filename, line_no)

            if source_line.strip().startswith('try:'):
                return self._trace_function
            
            # Vars defined / used (AST)
            vars_defined, vars_used = self._get_vars_defined_and_used(source_line)

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
            
            inherited_ids = []
            if self.inherited_control_stack:
                for e in self.inherited_control_stack[-1]:
                    tid = e.get('id')
                    ttruth = e.get('truth')
                    if ttruth is True:
                        inherited_ids.append(tid)
                    elif ttruth is False:
                        inherited_ids.append(-tid)
                    else:
                        inherited_ids.append(tid)

                        # Use a comment-free version for parsing/eval (but keep indent based on original)
            line_no_comments = self._strip_comments_preserving_strings(source_line)
            stripped_no_comments = line_no_comments.strip()

            # For AST, var-use detection etc already uses get_vars_defined_and_used -> which uses stripped_no_comments

            # When deciding if this line is a control header, use stripped_no_comments
            m = re.match(r'^(if|elif|for|while|with)\b', stripped_no_comments)
            if m:
                keyword = m.group(1)

                # capture event id to push later
                current_event_id = self.event_id

                truth_value = None
                try:
                    if keyword in ('if', 'elif', 'while'):
                        cond_m = re.match(r'^(?:if|elif|while)\s+(.*):\s*$', stripped_no_comments)
                        if cond_m:
                            cond_text = cond_m.group(1)
                            try:
                                cond_eval = eval(compile(cond_text, '<cond>', 'eval'),
                                                frame.f_globals, frame.f_locals)
                                truth_value = bool(cond_eval)
                            except Exception:
                                truth_value = False
                        else:
                            truth_value = False
                    elif keyword == 'for':
                        for_m = re.match(r'^for\s+.*\s+in\s+(.*):\s*$', stripped_no_comments)
                        if for_m:
                            iterable_text = for_m.group(1)
                            try:
                                iterable_val = eval(compile(iterable_text, '<iter>', 'eval'),
                                                    frame.f_globals, frame.f_locals)
                                truth_value = bool(iterable_val)
                            except Exception:
                                truth_value = False
                        else:
                            truth_value = False
                    elif keyword == 'with':
                        truth_value = True
                except Exception:
                    truth_value = False

                # Add the Line event (control_deps computed from current control_stack)
                seen_variables = self._get_current_seen_variables()
                self._add_trace_entry(
                    'Line',
                    frame,
                    vars_defined=vars_defined,
                    vars_used=vars_used,
                    control_dependencies=control_deps,
                    inherited_control_dependencies=inherited_ids,
                    seen_variables=seen_variables
                )
                
                self._pending_line_events[frame] = self.trace_data[-1]

                # Record last-definition event ids for any variables defined on this line
                if vars_defined:
                    cur_qualified = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"
                    for v in vars_defined:
                        self.last_def_event[cur_qualified][v] = self.event_id - 1

                # Now push the control entry using the event id assigned above
                self.control_stack.append({
                    'indent': indent,
                    'id': current_event_id,
                    'truth': truth_value
                })

            else:
                # Normal non-control line: just record it with the active control_deps
                seen_variables = self._get_current_seen_variables()
                self._add_trace_entry(
                    'Line',
                    frame,
                    vars_defined=vars_defined,
                    vars_used=vars_used,
                    control_dependencies=control_deps,
                    inherited_control_dependencies=inherited_ids,
                    seen_variables=seen_variables
                )
                
                self._pending_line_events[frame] = self.trace_data[-1]

                # Record last-definition event ids for any variables defined on this line
                if vars_defined:
                    cur_qualified = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"
                    for v in vars_defined:
                        self.last_def_event[cur_qualified][v] = self.event_id - 1

        elif event == 'exception':
            if self.call_stack:
                exc_type, exc_value, exc_tb = arg
                source_line = self._get_source_line(frame.f_code.co_filename, frame.f_lineno)
                offending_vars = []
                try:
                    words = re.findall(r"[A-Za-z_][A-Za-z_0-9]*", source_line)
                    for name in words:
                        if name in str(exc_value):
                            if f"'{name}'" in str(exc_value):
                                offending_vars.append(name)
                except Exception:
                        pass
                    
                self._add_trace_entry(
                    'Exception',
                    frame,
                    exception_type=exc_type.__name__,
                    exception_value=str(exc_value),
                    exception_variables=offending_vars or None
                )

        return self._trace_function
    
    def start_tracing(self):
        """Start the trace collection"""
        sys.settrace(self._trace_function)
        
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
