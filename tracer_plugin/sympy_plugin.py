import os
import sys
import threading

from tracer import ExecutionTracer

_state = threading.local()

def _looks_like_sympy_test(frame):
    co = frame.f_code
    if not co.co_name.startswith("test"):
        return None
    fn = (co.co_filename or "").replace("\\", "/")
    if "/sympy/" in fn and "/tests/" in fn and "/test_" in fn and fn.endswith(".py"):
        return co.co_name
    return None

def _profile(frame, event, arg):
    st = getattr(_state, "stack", None)
    if st is None:
        _state.stack = st = []
        _state.active = False
        _state.tid = None
        _state.tracer = None
    if event == "call":
        if not _state.active:
            tid = _looks_like_sympy_test(frame)
            if tid:
                _state.active = True
                _state.tid = tid
                _state.tracer = ExecutionTracer(os.path.join(os.environ.get('TRACER_OUTPUT_DIR'), "{}.jsonl".format(tid)))
                st.append("root")
                _state.tracer.start_tracing()
                return
        if _state.active:
            st.append("call")
    elif event == "return" and _state.active:
        if st:
            st.pop()
        if not st:
            _state.tracer.stop_tracing()
            try:
                _state.tracer.save_trace()
            except Exception as e:
                print("Failed to save trace to {}: {}".format(_state.tracer.output_file, e), file=sys.stderr, flush=True)
            _state.active = False
            _state.tid = None
            _state.tracer = None
        return

def _install():
    sys.setprofile(_profile)
    try:
        threading.setprofile(_profile)
    except Exception:
        pass

if os.environ.get("ENABLE_TRACER", "0") == "1":
    _install()