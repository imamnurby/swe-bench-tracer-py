# SWE-bench Python Tracer

`py-tracer` is a custom serialization and execution-tracing library for Python projects from the [SWE-bench](https://www.swebench.com/) benchmark.
It records Python execution as JSON Lines (JSONL) and converts common project objects into stable, useful data.

The package includes:

- A pytest plugin that traces test execution automatically.
- A context-manager API for tracing Python code directly.
- Serialization helpers that build JSON-compatible Python values.
- An expression inspector that reads values at a selected source line.
- Serializer extensions for common Python libraries and SWE-bench projects.

## Installation

Install the package from GitHub in the same environment as the project that you want to trace:

```shell
python -m pip install "py-tracer @ git+https://github.com/imamnurby/swe-bench-tracer-py.git"
```

The pytest integration needs pytest in the target project.
To also install the package's common optional dependencies, use the `all` extra:

```shell
python -m pip install "py-tracer[all] @ git+https://github.com/imamnurby/swe-bench-tracer-py.git"
```

The `all` extra installs pytest, Pydantic, NumPy, and pandas.
Other serializer extensions activate when their related libraries are present in the target environment.

## Quick start with pytest

The package registers its pytest plugin during installation.
Pass an output directory when you run a test:

```shell
python -m pytest tests/test_example.py --output ./traces
```

The plugin creates one `.jsonl` file for each traced test.
The path under the output directory is based on the pytest node ID.

Use `--test-name` to trace one exact node ID:

```shell
python -m pytest \
  --output ./traces \
  --test-name "tests/test_example.py::test_example"
```

The plugin is enabled by default after installation.
If you want to run pytest without the tracer, pass `--disable`:

```shell
python -m pytest --disable
```

## Trace selected functions

By default, the tracer records all project functions that it does not identify as standard-library, third-party, or tracer code.
Use `--allowed-functions` with a comma-separated list to restrict the trace.
Each value uses the `<module>:<qualified-function-name>` format.

```shell
python -m pytest tests/test_example.py \
  --output ./traces \
  --allowed-functions "my_project.math:add,my_project.service:Service.run"
```

Use `--include-stdlib` to include selected path components that the tracer would normally exclude:

```shell
python -m pytest tests/test_example.py \
  --output ./traces \
  --include-stdlib "my_dependency"
```

## Direct Python API

Use `ExecutionTracer` as a context manager when pytest is not the right entry point:

```python
from tracer import ExecutionTracer


def add(left, right):
    return left + right


with ExecutionTracer(output_file="trace.jsonl"):
    result = add(2, 3)

assert result == 5
```

The context manager starts tracing on entry and saves the trace when it exits.
An exception from the traced code is still raised after the trace is saved.

You can apply the same filters through the Python API:

```python
from tracer import ExecutionTracer


with ExecutionTracer(
    output_file="trace.jsonl",
    allowed_functions={"my_project.math:add"},
    include_stdlib={"my_dependency"},
):
    run_workload()
```

## Serialization API

The serializer provides three functions:

- `serialize(value)` returns a JSON-compatible Python value.
- `dump(value)` returns the serialized value as a JSON string.
- `deserialize(value)` restores a serialized Python value when a handler supports restoration.

```python
from tracer.serializer import deserialize, dump, serialize


payload = {"result": 5, "values": (1, 2, 3)}

encoded = serialize(payload)
json_text = dump(payload)
decoded = deserialize(encoded)
```

Pass the value from `serialize()` to `deserialize()`.
The `deserialize()` function does not parse the JSON string returned by `dump()`.

## Trace format

An execution trace is a JSONL file with one serialized event per line.
The tracer records these event types:

- `Function` for a function call and its serialized parameters.
- `Line` for an executed source line and its visible local values.
- `Return` for a function return and its serialized return value.
- `Exception` for an observed exception type and message.

Events can also include the source file, line number, statement, function name, caller, and dependency metadata.
Third-party objects use a matching serializer extension when one is available.

## Pytest options

### General and tracing options

| Option | Description |
| --- | --- |
| `--output PATH` | Write result files under `PATH`. This option is required while the plugin is enabled. |
| `--disable` | Run pytest without tracing or inspection. |
| `--mode tracer\|inspector` | Select normal tracing or expression inspection. The default is `tracer`. |
| `--allowed-functions LIST` | Trace only the comma-separated qualified function names. |
| `--include-stdlib LIST` | Include matching comma-separated path components that are normally excluded. |
| `--test-name NODE_ID` | Run the tracer only for the exact pytest node ID. |
| `--use-tracker` | Record call stacks with `Tracker` instead of full execution events. |

### Inspector options

Inspector mode evaluates an expression when execution reaches a selected source line.
The breakpoint file must be an absolute path.

```shell
python -m pytest tests/test_example.py \
  --mode inspector \
  --output ./inspections \
  --bp-file /absolute/path/to/my_project/module.py \
  --bp-line 42 \
  --expr "value" \
  --inspector-mode before
```

| Option | Description |
| --- | --- |
| `--bp-file PATH` | Set the absolute path of the breakpoint file. |
| `--bp-line NUMBER` | Set the positive breakpoint line number. |
| `--expr EXPRESSION` | Evaluate an expression at the breakpoint. |
| `--count NUMBER` | Inspect the selected breakpoint occurrence. The default is `1`. |
| `--inspector-mode before\|after` | Evaluate before or after the selected line. The default is `before`. |
| `--bp-func NAME` | Restrict the breakpoint to a function name. |

Inspector mode requires `--bp-file`, `--bp-line`, and `--expr`.
It cannot be combined with `--use-tracker`.

## Built-in serializer extensions

The package contains serializer extensions for:

- Python standard-library objects.
- Astropy.
- Django.
- Matplotlib.
- NumPy.
- pandas.
- Pylint.
- pytest.
- scikit-learn.
- Sphinx.
- SymPy.
- xarray.

Each extension handles only the related classes that it registers.
An optional library is not required merely because its extension exists.

## Add a serializer extension

Repository contributors can add support for more classes under `tracer/serializer/ext/`.
The serializer imports every Python module in this directory when `tracer.serializer` is first imported.

Create a module such as `tracer/serializer/ext/my_project.py`:

```python
from jsonpickle.handlers import BaseHandler, register


class WidgetHandler(BaseHandler):
    def flatten(self, obj, data):
        return {
            "py/object": "my_project.Widget",
            "name": obj.name,
        }

    def restore(self, data):
        from my_project import Widget

        return Widget(name=data["name"])


def register_handlers():
    from my_project import Widget

    register(Widget, WidgetHandler)
    return [Widget]
```

Follow these rules for a serializer extension:

1. Import optional dependencies inside `register_handlers()` or guard their imports with `try` and `except ImportError`.
2. Register each supported class with `jsonpickle`.
3. Return every registered class from `register_handlers()`.
4. Keep serialized output deterministic and remove volatile values such as memory addresses, timestamps, and temporary paths.
5. Add focused serialization and restoration tests when restoration is supported.

The repository-level extension modules are the supported extension mechanism.
The package does not yet expose a stable external serializer-plugin API.

## Development

Clone the repository and install it in editable mode:

```shell
git clone https://github.com/imamnurby/swe-bench-tracer-py.git
cd swe-bench-tracer-py
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

The installed pytest plugin remains active during development.
Use `--disable` when a test run must not generate traces.

The inspector tests can run as a focused pytest suite:

```shell
python -m pytest --disable \
  tests/test_inspector_mode_before.py \
  tests/test_inspector_mode_after.py
```

Some other files under `tests/` are executable validation scripts for specific serializers and integrations.
Their optional library requirements depend on the integration under test.

## Data safety

Trace files can contain function arguments, local variables, return values, file paths, and exception messages.
Treat trace files as sensitive data.
Review and sanitize them before you publish or share them.

Do not deserialize data from an untrusted source.
Deserializer handlers can reconstruct Python objects.

## License

This project is available under the MIT License.
See [LICENSE](LICENSE) for the full terms.
