import os
import bdb
import sys
import json
import signal
import traceback
import multiprocessing as mp

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
            if dbg.exprs_are_exc_or_return:
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
        
        @staticmethod
        def dispatch_exception(dbg: 'ExpressionInspector', frame, exc_info):
            if not dbg.break_here(frame):
                etype, evalue, tb = exc_info
                dbg.result['exception'] = {
                    "stage": "exception before breakpoint",
                    "type": etype.__name__,
                    "message": str(evalue),
                    "traceback": traceback.format_tb(tb),
                }
                return AfterExecution.Initialized
            dbg.count -= 1
            if dbg.count > 0:
                return AfterExecution.Initialized
            frame.f_locals['__exception__'] = [exc_info[0].__name__, str(exc_info[1])]
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
        
        @staticmethod
        def dispatch_exception(dbg: 'ExpressionInspector', frame, exc_info):
            raise RuntimeError("unreachable")

class BeforeExecution:
    class Initialized(State):
        @staticmethod
        def dispatch_line(dbg: 'ExpressionInspector', frame):
            if not dbg.break_here(frame):
                return BeforeExecution.Initialized
            if dbg.exprs_are_exc_or_return:
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
        
        @staticmethod
        def dispatch_exception(dbg: 'ExpressionInspector', frame, exc_info):
            if not dbg.break_here(frame):
                etype, evalue, tb = exc_info
                dbg.result['exception'] = {
                    "stage": "exception before breakpoint",
                    "type": etype.__name__,
                    "message": str(evalue),
                    "traceback": traceback.format_tb(tb),
                }
                return BeforeExecution.Initialized
            dbg.count -= 1
            if dbg.count > 0:
                return BeforeExecution.Initialized
            frame.f_locals['__exception__'] = [exc_info[0].__name__, str(exc_info[1])]
            dbg.eval_expr(frame)
            return Completed

class ExpressionInspector(bdb.Bdb):
    def __init__(self, bp_file: str, bp_line: int, expr: str | list[str], 
                 save_path: str = None, count: int = 1, 
                 mode: str = 'before'):
        super().__init__()
        assert os.path.isabs(bp_file), "bp_file must be an absolute path"
        assert count > 0, "count must be positive"
        assert mode in ['before', 'after'], "mode must be 'before' or 'after'"
        self.state = get_initial_state(mode)
        self.source_line = get_source_code_line(bp_file, bp_line).strip()
        self.expr = expr if isinstance(expr, list) else [expr]
        self.count = count
        self.save_path = save_path
        self.result = {
            'mode': mode,
            'file': bp_file,
            'line': bp_line,
            'count': self.count,
            'expr': self.expr,
            'value': None,
            'exception': {
                'stage': 'not reached',
                'type': None,
                'message': None,
                'traceback': None,
            },
        }
        self.exprs_are_exc_or_return = self._exprs_are_exc_or_return()
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
        self.state = self.state.dispatch_exception(self, frame, exc_info)
    
    def _exprs_are_exc_or_return(self):
        if all('__exception__' in expr or '__return__' in expr for expr in self.expr):
            return True
        if all('__exception__' not in expr and '__return__' not in expr for expr in self.expr):
            return False
        self.result['exception'] = {
            'stage': 'initialization',
            'type': 'RuntimeError',
            'message': "Mixed expressions with and without __exception__/__return__",
            'traceback': [],
        }
        self.set_quit()
        raise RuntimeError("unreachable")
    
    @staticmethod
    def fork_eval(queue, frame, expr, idx, timeout=60):
        def _timeout_handler(signum, frame):
            raise TimeoutError("Expression evaluation timed out")
        
        if '__return__' in expr and '__exception__' in frame.f_locals:
            expr = '__exception__'
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
        try:
            value = eval(expr, frame.f_globals, frame.f_locals)
            serialized = serialize(value)
            queue.put({
                'idx': idx,
                'value': serialized,
                'exception': None,
            })
        except Exception as e:
            queue.put({
                'idx': idx,
                'value': None,
                'exception': {
                    'stage': 'evaluation',
                    'type': type(e).__name__,
                    'message': str(e),
                    'traceback': traceback.format_tb(e.__traceback__),
                }
            })
        finally:
            signal.alarm(0)
    
    def eval_expr(self, frame):
        queue = mp.Queue()
        procs = [mp.Process(target=self.fork_eval, args=(queue, frame, expr, idx))
                 for idx, expr in enumerate(self.expr)]
        for p in procs: p.start()
        for p in procs: p.join()
        results = [queue.get() for _ in range(len(self.expr))]
        results.sort(key=lambda x: x['idx'])
        self.result['value'] = []
        self.result['exception'] = []
        for result in results:
            if result['exception'] is None:
                self.result['value'].append(result['value'])
                self.result['exception'].append(None)
            else:
                self.result['value'].append(None)
                self.result['exception'].append(result['exception'])   
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
