import pytest

def pytest_addoption(parser):
    group = parser.getgroup("tracer")
    group.addoption(
        '--output', help='Output directory for tracer results', required=True
    )

def pytest_configure(config):
    output_dir = config.getoption('--output')
    config._tracer_output_dir = output_dir

def pytest_unconfigure(config):
    del config._tracer_output_dir

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    '''
    Wraps the test call to trace its execution. Setup and teardown are not traced.
    '''
    cfg = item.config
    output_dir = getattr(cfg, '_tracer_output_dir', None)
    assert output_dir is not None, "Tracer output directory not set"
    
    