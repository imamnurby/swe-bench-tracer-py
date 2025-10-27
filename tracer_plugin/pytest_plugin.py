import os
import pytest

from tracer import ExecutionTracer

def pytest_addoption(parser):
    group = parser.getgroup("tracer")
    group.addoption(
        '--output', help='Output directory for tracer results', required=True
    )
    group.addoption(
        '--disable-tracer', help='Disable the tracer plugin', action='store_true', default=False
    )

def pytest_configure(config):
    config._tracer_output_dir = config.getoption('--output')
    config._is_tracer_disabled = config.getoption('--disable-tracer')

def pytest_unconfigure(config):
    del config._tracer_output_dir, config._is_tracer_disabled

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    cfg = item.config
    if cfg._is_tracer_disabled:
        yield
        return
    test_name = item.nodeid
    output_file = os.path.join(cfg._tracer_output_dir, "{}.jsonl".format(test_name))
    with ExecutionTracer(output_file):
        yield    
