import sys
import os
import ast
import json
import re
import copy
import io, tokenize
import inspect

from collections import defaultdict
from typing import Any, Dict, List, Tuple, Optional, Set, Match, Callable
from types import FrameType
from functools import wraps
from pathlib import Path
from tracer.util import get_func_qualname, call_signature, sanitize_for_json

import jsonpickle
import jsonpickle.ext.numpy as jsonpickle_numpy
import jsonpickle.ext.pandas as jsonpickle_pandas
jsonpickle_numpy.register_handlers()
jsonpickle_pandas.register_handlers()

def trace(prefix: str = ""):
    '''
    Decorator to trace a function's execution and save to a JSONL file.
    File name is derived from function signature and actual arguments.
    Only put on top of the entry function to be traced.
    '''
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs): # type: ignore
                sig = call_signature(func, *args, **kwargs)
                with ExecutionTracer(os.path.join(prefix, sig + ".jsonl")):
                    return await func(*args, **kwargs)
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                sig = call_signature(func, *args, **kwargs)
                with ExecutionTracer(os.path.join(prefix, sig + ".jsonl")):
                    return func(*args, **kwargs)
        return wrapper
    return decorator

class ExecutionTracer:
    def __init__(self, output_file: str = "trace.jsonl"):
        self.call_stack = []
        self.call_graph = defaultdict(set)
        self.call_counts = defaultdict(int)
        self.max_depth = 0
        self.trace_data = []
        self.output_file = output_file
        self.source_cache = {} 
        self.event_id = 0
        self.control_stack = []
        self.inherited_control_stack = []
        self.control_stack_stack = []     
        self.last_def_event = defaultdict(dict)
        self._pending_line_events = {}
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
        try:
            self.save_trace()
        except Exception as e:
            print(f"Failed to save trace to {self.output_file}: {e}", file=sys.stderr, flush=True)
        return False
    
    def _get_vars_defined_and_used(self, source_line: str) -> Tuple[List[str], List[str]]:
        """Return separate lists of variables defined and used in the statement."""
        defined, used = set(), set()
        if not source_line or not source_line.strip():
            return [], []

        code_no_comments = self._strip_comments_preserving_strings(source_line).rstrip()
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
    
    def _should_ignore(self, filename: str)->bool:
        """Check if the call is from a standard library or test framework"""
        if not filename:
            return False

        # Check for built-in modules
        if filename.startswith('<frozen'):
            return True
    
        # Exclude tracer's pytest plugin module
        if 'tracer_pytest' in filename:
            return True
        
        # Normalize the path
        normalized_path = os.path.normpath(filename)
        path_parts = normalized_path.split(os.sep)
        
        # Check if any part of the path matches stdlib modules
        if any(part in self.stdlib_modules for part in path_parts):
            return True

        # Exclude calls to third-party libraries
        if 'site-packages' in normalized_path:
            return True
            
        # Check if it's in the standard Python installation
        python_paths = [
            'lib/python',
            'Lib\\',
            '/usr/lib/python',
            '/usr/local/lib/python'
        ]
        
        if any(py_path in normalized_path for py_path in python_paths):
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
            for tok in tokenize.generate_tokens(io.StringIO(line).readline):
                if tok.type == tokenize.COMMENT:
                    continue
                tokens.append((tok.type, tok.string))
            return tokenize.untokenize(tokens)
        except Exception:
            return line.split('#', 1)[0]

    def _get_call_arg_varnames_from_call_line(self, source_line: str, callee_func_name: str)->Tuple[List, Dict]:
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
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return jsonpickle.encode(value)

    def _serialize_dict_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize each value in a dictionary."""
        return {key: self._serialize_value(value) for key, value in data.items()}
    
    def _get_function_parameters(self, frame: FrameType) -> Dict[str, Any]:
        """Extract function parameters and their values"""
        code = frame.f_code
        param_names = code.co_varnames[:code.co_argcount]
        params = {}
        
        for name in param_names:
            if name in frame.f_locals:
                params[name] = self._serialize_value(frame.f_locals[name])
        
        # Handle *args and **kwargs
        if code.co_flags & 0x04: 
            varargs_name = code.co_varnames[code.co_argcount]
            if varargs_name in frame.f_locals:
                params['*' + varargs_name] = self._serialize_value(frame.f_locals[varargs_name])
                
        if code.co_flags & 0x08: 
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
        
    def _get_function_info(self, frame: FrameType)->Dict[str, Any]:
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
    
    def _update_function_variables(self, frame: FrameType)->None:
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
    
    def _add_trace_entry(self, event_type: str, frame: FrameType, **kwargs)->None:
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

    def _trace_function(self, frame: FrameType, event: str, arg: Any) -> Optional[Callable]:
        """The main tracing callback that dispatches events to their respective handlers."""
    
        if event == 'call' and frame.f_locals.get('self') is self:
            return None

        func_info = self._get_function_info(frame)
        if self._should_ignore(func_info['filename']):
            return self._trace_function
        
        if event == 'call':
            self._handle_call_event(frame, func_info)
        elif event == 'return':
            self._handle_return_event(frame, arg)
        elif event == 'line':
            self._handle_line_event(frame)
        elif event == 'exception':
            self._handle_exception_event(frame, arg)
        return self._trace_function
    
    def _handle_call_event(self, frame: FrameType, func_info: Dict[str, Any]) -> None:
        """Handles a 'call' event by managing stacks, computing parameter sources, and recording function entry."""
        caller_snapshot = self._snapshot_caller_context()
        self._prepare_call_stacks()
        parameters = self._get_function_parameters(frame)
        func_vars = dict(parameters)
        self.function_variables_stack.append(func_vars)
        parameter_sources = self._compute_parameter_sources(frame, func_info)
        self._update_call_graph(func_info)
        self.call_stack.append(func_info)
        self._record_function_entry(frame, func_info, parameters, parameter_sources, caller_snapshot)


    def _snapshot_caller_context(self) -> List[Dict[str, Any]]:
        """Creates a snapshot of the current and inherited control stacks for the calling context."""
        caller_snapshot = [dict(e) for e in self.control_stack]
        if self.inherited_control_stack:
            caller_snapshot.extend([dict(e) for e in self.inherited_control_stack[-1]])
        self.inherited_control_stack.append(caller_snapshot)
        return caller_snapshot


    def _prepare_call_stacks(self) -> None:
        """Prepares the control and call stacks for a new function call and updates max depth."""
        self.control_stack_stack.append(self.control_stack)
        self.control_stack = []

        current_depth = len(self.call_stack)
        self.max_depth = max(self.max_depth, current_depth)


    def _compute_parameter_sources(self, frame: FrameType, func_info: Dict[str, Any]) -> Dict[str, Optional[List[Dict[str, Any]]]]:
        """Determines the source variables in the caller's frame for each parameter of the current function."""
        parameter_sources = {}

        caller_frame = frame.f_back
        caller_qualified = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"

        code = frame.f_code
        param_count = code.co_argcount
        param_names = list(code.co_varnames[:param_count])

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

        # Parse caller source
        pos_arg_vars, kw_arg_vars = [], {}
        try:
            if caller_frame is not None:
                caller_src = self._get_source_line(caller_frame.f_code.co_filename, caller_frame.f_lineno)
                pos_arg_vars, kw_arg_vars = self._get_call_arg_varnames_from_call_line(
                    caller_src, func_info['func_name']
                )
        except Exception:
            pos_arg_vars, kw_arg_vars = [], {}

        fixed_count = param_count
        for i, pname in enumerate(param_names):
            found_varnames = []

            if pname in kw_arg_vars:
                found_varnames = kw_arg_vars.get(pname, []) or []
            elif i < fixed_count:
                if i < len(pos_arg_vars):
                    found_varnames = pos_arg_vars[i] or []
            elif varargs_name is not None and pname == varargs_name:
                extra = pos_arg_vars[fixed_count:] if len(pos_arg_vars) > fixed_count else []
                agg = []
                for sub in extra:
                    agg.extend(sub)
                found_varnames = agg
            elif kwargs_name is not None and pname == kwargs_name:
                found_varnames = kw_arg_vars.get('__KW_EXPANSION__', []) or []

            # Fallback heuristic
            if not found_varnames and caller_frame is not None:
                raw_val = frame.f_locals.get(pname, None)
                found_names = []
                for cname, cval in caller_frame.f_locals.items():
                    try:
                        if raw_val is cval or raw_val == cval:
                            found_names.append(cname)
                    except Exception:
                        pass
                found_varnames = list(dict.fromkeys(found_names))

            # Map varnames → event_id
            if found_varnames:
                mapped = []
                for vname in found_varnames:
                    src_event = self.last_def_event.get(caller_qualified, {}).get(vname)
                    mapped.append({"var": vname, "event_id": src_event})
                parameter_sources[pname] = mapped
            else:
                parameter_sources[pname] = None

        return parameter_sources


    def _update_call_graph(self, func_info: Dict[str, Any]) -> None:
        """Updates the call graph by adding an edge from the caller to the callee."""
        if self.call_stack:
            caller_info = self.call_stack[-1]
            caller_name = caller_info['qualified_name']
            callee_name = func_info['qualified_name']
            self.call_graph[caller_name].add(callee_name)
            self.call_counts[(caller_name, callee_name)] += 1


    def _record_function_entry(self, frame: FrameType, func_info: Dict[str, Any], parameters: Dict[str, Any], parameter_sources: Dict[str, Optional[List[Dict[str, Any]]]], caller_snapshot: List[Dict[str, Any]]) -> None:
        """Records a 'Function' entry in the trace data and marks the definition event for its parameters."""
        self._add_trace_entry(
            'Function',
            frame,
            function_name=func_info['qualified_name'],
            caller_name=self.call_stack[-2]['qualified_name'] if len(self.call_stack) > 1 else "<module>",
            parameters=parameters,
            parameter_sources=parameter_sources if parameter_sources else {},
            inherited_control_dependencies=[
                e['id'] if e.get('truth') is not False else -e['id']
                for e in caller_snapshot
            ]
        )

        # Mark callee parameter definitions
        callee_qualified = func_info['qualified_name']
        code = frame.f_code
        param_count = code.co_argcount
        param_names = list(code.co_varnames[:param_count])
        if code.co_flags & 0x04:
            param_names.append(code.co_varnames[param_count])
            param_count += 1
        if code.co_flags & 0x08:
            param_names.append(code.co_varnames[param_count])

        for pname in param_names:
            self.last_def_event[callee_qualified][pname] = self.event_id - 1


    def _handle_return_event(self, frame: FrameType, arg: Any) -> None:
        """Handles a 'return' event by restoring caller state from stacks and recording the return."""
        if self.control_stack_stack:
            self.control_stack = self.control_stack_stack.pop()
        else:
            self.control_stack = []

        returning_func_name = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"
        caller_name_after_return = (
            self.call_stack[-2]['qualified_name']
            if len(self.call_stack) > 1 else
            "<module>" if len(self.call_stack) == 1 else None
        )

        if self.call_stack:
            self.call_stack.pop()
            source_line = self._get_source_line(frame.f_code.co_filename, frame.f_lineno)
            _, vars_used = self._get_vars_defined_and_used(source_line)
            if frame in self._pending_line_events:
                prev_event = self._pending_line_events.pop(frame)
                prev_event['seen_variables'] = self._serialize_dict_values(dict(frame.f_locals))

            if self.function_variables_stack:
                self.function_variables_stack.pop()
            if self.inherited_control_stack:
                self.inherited_control_stack.pop()

            self._add_trace_entry(
                'Return',
                frame,
                function_name=returning_func_name,
                vars_used=vars_used,
                caller_name=caller_name_after_return,
                return_value=self._serialize_value(arg)
            )

    def _handle_line_event(self, frame: FrameType) -> Optional[Callable]:
        """Handles a 'line' event by analyzing the line and dispatching to control or regular line handlers."""
        self._finalize_pending_line_event(frame)
        self._update_function_variables(frame)

        filename, line_no, source_line, stripped, stripped_no_comments, indent = self._compute_line_metadata(frame)
        if stripped.startswith('try:'):
            return self._trace_function

        vars_defined, vars_used = self._get_vars_defined_and_used(source_line)
        is_elif_else = stripped.startswith(('elif', 'else', 'except', 'finally'))

        # Manage control stack indentation rules
        self._update_control_stack_for_indent(indent, is_elif_else)

        control_deps, inherited_ids = self._compute_control_dependencies()

        # Determine if this is a control-header line (if/for/while/with)
        m = re.match(r'^(if|elif|for|while|with)\b', stripped_no_comments)
        if m:
            self._handle_control_header_line(frame, m, vars_defined, vars_used, control_deps, inherited_ids,
                                            stripped_no_comments, indent)
        else:
            self._handle_regular_line(frame, vars_defined, vars_used, control_deps, inherited_ids)

    def _handle_exception_event(self, frame: FrameType, arg: Tuple[type, BaseException, Any]) -> None:
        """Handles an 'exception' event by recording the exception details in the trace."""
        if self.call_stack:
            exc_type, exc_value, exc_tb = arg
            source_line = self._get_source_line(frame.f_code.co_filename, frame.f_lineno)
            _, vars_used = self._get_vars_defined_and_used(source_line)

            self._add_trace_entry(
                'Exception',
                frame,
                exception_type=exc_type.__name__,
                exception_value=str(exc_value),
                vars_used=vars_used or None
            )

    def _finalize_pending_line_event(self, frame: FrameType) -> None:
        """Updates the previously recorded pending line event with the final state of local variables."""
        if frame in self._pending_line_events:
            prev_event = self._pending_line_events.pop(frame)
            prev_event['seen_variables'] = self._serialize_dict_values(dict(frame.f_locals))

    def _compute_line_metadata(self, frame: FrameType) -> Tuple[str, int, str, str, str, int]:
        """Gathers and computes metadata for the current line being executed, such as source and indentation."""
        filename = frame.f_code.co_filename
        line_no = frame.f_lineno
        source_line = self._get_source_line(filename, line_no)
        stripped = source_line.strip()
        line_no_comments = self._strip_comments_preserving_strings(source_line)
        stripped_no_comments = line_no_comments.strip()
        indent = self._line_indent(source_line)
        return filename, line_no, source_line, stripped, stripped_no_comments, indent


    def _update_control_stack_for_indent(self, indent: int, is_elif_else: bool) -> None:
        """Manages the control flow stack by popping entries based on changes in code indentation."""
        if is_elif_else:
            while self.control_stack and indent < self.control_stack[-1]['indent']:
                self.control_stack.pop()
        else:
            while self.control_stack and indent <= self.control_stack[-1]['indent']:
                self.control_stack.pop()


    def _compute_control_dependencies(self) -> Tuple[List[int], List[int]]:
        """Computes the list of current and inherited control dependencies for the current event."""
        control_deps = []
        for entry in self.control_stack:
            eid = entry['id']
            truth = entry.get('truth')
            if truth is True:
                control_deps.append(eid)
            elif truth is False:
                control_deps.append(-eid)
            else:
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

        return control_deps, inherited_ids


    def _handle_control_header_line(self, frame: FrameType, match: Match[str], vars_defined: List[str], vars_used: List[str],
                                    control_deps: List[int], inherited_ids: List[int], stripped_no_comments: str, indent: int) -> None:
        """Handles a line that starts a control flow block, evaluating its condition and updating the control stack."""
        keyword = match.group(1)
        current_event_id = self.event_id

        # Determine truth value (same logic)
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

        if vars_defined:
            self._update_last_definitions(vars_defined)

        self.control_stack.append({
            'indent': indent,
            'id': current_event_id,
            'truth': truth_value
        })


    def _handle_regular_line(self, frame: FrameType, vars_defined: List[str], vars_used: List[str], control_deps: List[int], inherited_ids: List[int]) -> None:
        """Handles a regular line of code by recording a 'Line' event with its data dependencies."""
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

        if vars_defined:
            self._update_last_definitions(vars_defined)


    def _update_last_definitions(self, vars_defined: List[str]) -> None:
        """Updates the mapping of variable names to the event ID where they were last defined."""
        cur_qualified = self.call_stack[-1]['qualified_name'] if self.call_stack else "<module>"
        for v in vars_defined:
            self.last_def_event[cur_qualified][v] = self.event_id - 1

    def start_tracing(self):
        """Start the trace collection"""
        sys.settrace(self._trace_function)
        
    def stop_tracing(self):
        """Stop the trace collection"""
        sys.settrace(None)
        
    def save_trace(self):
        """Save the collected trace data to JSONL file"""
        # Ensure output directory exists
        base_dir = os.path.dirname(self.output_file)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)
        with open(self.output_file, 'w') as f:
            for entry in self.trace_data:
                try:
                    json_line = json.dumps(entry, ensure_ascii=False)
                    f.write(json_line + '\n')
                except TypeError:
                    sanitized_entry = sanitize_for_json(entry)
                    json_line = json.dumps(sanitized_entry, ensure_ascii=False)
                    f.write(json_line + '\n')
        print(f"Trace saved to {self.output_file}", file=sys.stderr, flush=True)
        
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
