import os
import pytest

from tracer import Tracker, ExecutionTracer, ExpressionInspector

def validate_options(config):
    if config._disable:
        return
    assert config._output is not None, "--output must be specified when tracer is enabled"
    if config._mode == 'tracer':
        return
    if config._mode == 'inspector':
        assert config._bp_file is not None, "--bp-file must be specified in inspector mode"
        assert config._bp_line is not None, "--bp-line must be specified in inspector mode"
        assert config._expr is not None, "--expr must be specified in inspector mode"

def pytest_addoption(parser):
    group = parser.getgroup("tracer")
    # General options
    group.addoption('--mode', choices=['tracer', 'inspector'], default='tracer')
    group.addoption('--output', default=None)
    group.addoption('--disable', action='store_true', default=False)
    # Inspector-specific options
    group.addoption('--bp-file', default=None)
    group.addoption('--bp-line', type=int, default=None)
    group.addoption('--expr', default=None)
    group.addoption('--count', type=int, default=1)
    group.addoption('--inspector-mode', choices=['before', 'after'], default='before')
    # Tracker-specific options
    group.addoption('--use-tracker', action='store_true', default=False)
    # Optional options
    group.addoption('--test-name', default=None)
    group.addoption('--include-stdlib', default=None)

def pytest_configure(config):
    config._mode = config.getoption('--mode')
    config._output = config.getoption('--output')
    config._disable = config.getoption('--disable')
    config._bp_file = config.getoption('--bp-file')
    config._bp_line = config.getoption('--bp-line')
    config._expr = config.getoption('--expr')
    config._count = config.getoption('--count')
    config._inspector_mode = config.getoption('--inspector-mode')
    config._use_tracker = config.getoption('--use-tracker')
    config._test_name = config.getoption('--test-name')
    _inc = config.getoption('--include-stdlib')
    if _inc is None or _inc.strip().lower() == 'none':
        config._include_stdlib = set()
    else:
        config._include_stdlib = set(s.strip() for s in _inc.split(',') if s.strip())
    try:
        validate_options(config)
    except AssertionError as e:
        raise pytest.UsageError(e)

def pytest_unconfigure(config):
    del config._mode, config._output, config._disable, config._bp_file
    del config._bp_line, config._expr, config._count, config._inspector_mode
    del config._use_tracker, config._test_name, config._include_stdlib

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    config = item.config
    if config._disable:
        yield
        return
    test_name = item.nodeid
    if config._test_name is not None and config._test_name != test_name:
        yield
        return
    output_file = os.path.join(config._output, "{}.jsonl".format(test_name))
    if config._mode == 'tracer':
        if config._use_tracker:
            with Tracker(output_file=output_file):
                yield
            return
        else:
            with ExecutionTracer(output_file=output_file, include_stdlib=config._include_stdlib):
                yield
            return
    if config._mode == 'inspector':
        with ExpressionInspector(
            config._bp_file,
            config._bp_line,
            config._expr,
            save_path=output_file,
            count=config._count,
            mode=config._inspector_mode,
        ):
            outcome = yield
            outcome.force_result(None)
        return
