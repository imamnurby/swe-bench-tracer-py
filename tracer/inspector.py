import os
import bdb
import sys
import json
import traceback

from tracer.serializer import serialize

__all__ = ['ExpressionInspector']

def get_source_code_line(file_path: str, lineno: int) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if lineno < 1 or lineno > len(lines):
        raise ValueError("Line number out of range")
    return lines[lineno - 1]

def get_initial_state(mode: str):
    if mode == 'before':
        return BeforeExecution.Initialized
    elif mode == 'after':
        return AfterExecution.Initialized
    raise RuntimeError("unreachable")

# State Machine Diagram
# A. Non-return statement breakpoint
# A.1. Mode "after": Inspect expression after bp line is executed
#
#                 <bp reached>
#    INITIALIZED -------------> BREAKPOINT ------------> COMPLETED
#      ↖-----|     [set next]               [eval expr]    ↖---|
#  <bp not reached>
#
# A.2. Mode "before": Inspect expression before bp line is executed
#
#                      <bp reached>
#    INITIALIZED -----------------------> COMPLETED
#      ↖-----|          [eval expr]         ↖---|
#  <bp not reached>
#
# B. Return statement breakpoint: Same as A.2
#
# - bp: <file:line:count>, count is decremented on each hit until 0
# - when count is 0, the bp is considered "reached"
class State:
    @staticmethod
    def dispatch_line(dbg: 'ExpressionInspector', frame):
        raise NotImplementedError("Must be implemented by subclasses")
    
    @staticmethod
    def dispatch_return(dbg: 'ExpressionInspector', frame, return_value):
        raise NotImplementedError("Must be implemented by subclasses")

class Completed(State):
    @staticmethod
    def dispatch_line(dbg: 'ExpressionInspector', frame):
        raise RuntimeError("Inspection already completed")
    
    @staticmethod
    def dispatch_return(dbg: 'ExpressionInspector', frame, return_value):
        raise RuntimeError("Inspection already completed")

class AfterExecution:
    class Initialized(State):
        @staticmethod
        def dispatch_line(dbg: 'ExpressionInspector', frame):
            if not dbg.break_here(frame):
                return AfterExecution.Initialized
            if dbg.source_line.startswith('return'):
                return AfterExecution.Initialized
            dbg.count -= 1
            if dbg.count > 0:
                return AfterExecution.Initialized
            dbg.set_next(frame)
            return AfterExecution.Breakpoint

        @staticmethod
        def dispatch_return(dbg: 'ExpressionInspector', frame, return_value):
            if not dbg.break_here(frame):
                return AfterExecution.Initialized
            dbg.count -= 1
            if dbg.count > 0:
                return AfterExecution.Initialized
            frame.f_locals['__return__'] = return_value
            dbg.eval_expr(frame)
            return Completed

    class Breakpoint(State):
        @staticmethod
        def dispatch_line(dbg: 'ExpressionInspector', frame):
            dbg.eval_expr(frame)
            return Completed
        
        @staticmethod
        def dispatch_return(dbg: 'ExpressionInspector', frame, return_value):
            raise RuntimeError("unreachable")

class BeforeExecution:
    class Initialized(State):
        @staticmethod
        def dispatch_line(dbg: 'ExpressionInspector', frame):
            if not dbg.break_here(frame):
                return BeforeExecution.Initialized
            if dbg.source_line.startswith('return'):
                return BeforeExecution.Initialized
            dbg.count -= 1
            if dbg.count > 0:
                return BeforeExecution.Initialized
            dbg.eval_expr(frame)
            return Completed

        @staticmethod
        def dispatch_return(dbg: 'ExpressionInspector', frame, return_value):
            if not dbg.break_here(frame):
                return BeforeExecution.Initialized
            dbg.count -= 1
            if dbg.count > 0:
                return BeforeExecution.Initialized
            frame.f_locals['__return__'] = return_value
            dbg.eval_expr(frame)
            return Completed

class ExpressionInspector(bdb.Bdb):
    def __init__(self, bp_file: str, bp_line: int, expr: str, 
                 save_path: str = None, count: int = 1, 
                 mode: str = 'before'):
        super().__init__()
        assert os.path.isabs(bp_file), "bp_file must be an absolute path"
        assert count > 0, "count must be positive"
        assert mode in ['before', 'after'], "mode must be 'before' or 'after'"
        self.state = get_initial_state(mode)
        self.source_line = get_source_code_line(bp_file, bp_line).strip()
        self.expr = expr
        self.count = count
        self.save_path = save_path
        self.result = {
            'mode': mode,
            'file': bp_file,
            'line': bp_line,
            'count': count,
            'expr': expr,
            'value': None,
            'exception': {
                'stage': 'not reached',
                'type': None,
                'message': None,
                'traceback': None,
            },
        }
        self.set_break(filename=bp_file, lineno=bp_line)
    
    def __enter__(self):
        self.set_trace()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.save_result()
        return True # Suppress exceptions
    
    def user_line(self, frame):
        self.state = self.state.dispatch_line(self, frame)
    
    def user_return(self, frame, return_value):
        self.state = self.state.dispatch_return(self, frame, return_value)
    
    def user_exception(self, frame, exc_info):
        etype, evalue, tb = exc_info
        self.result['exception'] = {
            "stage": "exception before breakpoint",
            "type": etype.__name__,
            "message": str(evalue),
            "traceback": traceback.format_tb(tb),
        }
    
    def eval_expr(self, frame):
        try:
            value = eval(self.expr, frame.f_globals, frame.f_locals)
            self.result['value'] = serialize(value)
            self.result['exception'] = None
        except Exception as e:
            self.result['exception'] = {
                'stage': 'evaluation',
                'type': type(e).__name__,
                'message': str(e),
                'traceback': traceback.format_tb(e.__traceback__),
            }
        self.set_quit()
    
    def save_result(self):
        if not self.save_path:
            return
        base_dir = os.path.dirname(self.save_path)
        if not os.path.exists(base_dir):
            os.makedirs(base_dir, exist_ok=True)
        with open(self.save_path, 'w', encoding='utf-8') as f:
            json.dump(self.result, f, indent=2)
        print("Expression value saved to {}".format(self.save_path), file=sys.stderr, flush=True)
