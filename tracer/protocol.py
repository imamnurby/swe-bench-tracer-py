import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

REPR_PATTERN = re.compile(r'<(?P<object>[^>]+?) object at 0x[0-9a-fA-F]+>')

def sanitize_repr_address(value: str) -> str:
    def _strip_address(match: re.Match) -> str:
        return f"<{match.group('object')}>"

    return REPR_PATTERN.sub(_strip_address, value)

class Event(BaseModel):
    event_id: int
    event_type: str
    line_number: int
    statement: str
    filepath: str
    function_name: str
    excluded: bool = False
    
    @staticmethod
    def from_dict(data):
        event_type = data['event_type']
        if event_type == 'Function':
            event = FunctionEvent(**data)
            return event
        elif event_type == 'Return':
            event = ReturnEvent(**data)
            return event
        elif event_type == 'Exception':
            return ExceptionEvent(**data)
        elif event_type == 'Line':
            event = LineEvent(**data)
            return event
        else:
            raise ValueError(f"Unknown event type: {event_type}")

    def matches(self, other):
        if not isinstance(other, Event):
            return False
        if isinstance(self, FunctionEvent) and isinstance(other, FunctionEvent):
            return self.function_name == other.function_name
        return (self.event_type == other.event_type and
                self.statement == other.statement and
                self.function_name == other.function_name)

    def dump(self):
        return self.model_dump(exclude={
            "event_id", "event_type", "line_number", "statement", "excluded",
        })

class FunctionEvent(Event):
    caller_name: str
    parameters: Dict[str, Any]
    parameter_sources: Dict
    inherited_control_dependencies: List[int]

    def dump(self):
        return self.model_dump(exclude={
            "event_id", "event_type", "line_number", "statement", "excluded",
            "inherited_control_dependencies",
        })

class ReturnEvent(Event):
    vars_used: List[str]
    caller_name: str
    return_value: Any

    def dump(self):
        return self.model_dump(exclude={
            "event_id", "event_type", "line_number", "statement", "excluded",
            "vars_used", "caller_name",
        })

class ExceptionEvent(Event):
    exception_type: str
    exception_value: str
    vars_used: Optional[List[str]] = None

    def dump(self):
        copied = self.model_copy(update={"exception_value": sanitize_repr_address(self.exception_value)})
        return copied.model_dump(exclude={
            "event_id", "event_type", "line_number", "statement", "excluded",
            "vars_used",
        })

class LineEvent(Event):
    vars_defined: List[str]
    vars_used: List[str]
    control_dependencies: List[int]
    inherited_control_dependencies: List[int]
    seen_variables: Dict[str, Any]

    def dump(self):
        if self.function_name.startswith("sklearn"):
            obj = self.model_copy()
            if "cachedir" in obj.seen_variables:
                obj.seen_variables["cachedir"] = "<tmpdir>"
        elif self.function_name.endswith("AdminScriptTestCase.write_settings"):
            obj = self.model_copy()
            if "settings_file_path" in obj.seen_variables:
                var = obj.seen_variables["settings_file_path"]
                obj.seen_variables["settings_file_path"] = os.path.join("<tmpdir>", os.path.basename(var))
            if "settings_file" in obj.seen_variables:
                var = obj.seen_variables["settings_file"]
                if var and "name" in var:
                    obj.seen_variables["settings_file"]["name"] = os.path.join("<tmpdir>", os.path.basename(var["name"]))
        elif self.function_name.endswith("AdminScriptTestCase.run_manage"):
            obj = self.model_copy()
            if "test_manage_py" in obj.seen_variables:
                var = obj.seen_variables["test_manage_py"]
                obj.seen_variables["test_manage_py"] = os.path.join("<tmpdir>", os.path.basename(var))
            if "fp" in obj.seen_variables:
                var = obj.seen_variables["fp"]
                if var and "name" in var:
                    obj.seen_variables["fp"]["name"] = os.path.join("<tmpdir>", os.path.basename(var["name"]))
        elif self.function_name.endswith("AdminScriptTestCase.run_test"):
            obj = self.model_copy()
            if "base_dir" in obj.seen_variables:
                obj.seen_variables["base_dir"] = "<tmpdir>"
            if "settings_file" in obj.seen_variables:
                var = obj.seen_variables["settings_file"]
                if var and "name" in var:
                    obj.seen_variables["settings_file"]["name"] = os.path.join("<tmpdir>", os.path.basename(var["name"]))
            if "test_environ" in obj.seen_variables:
                del obj.seen_variables["test_environ"]
            if "python_path" in obj.seen_variables:
                obj.seen_variables["python_path"][0] = "<tmpdir>"
        elif self.function_name.endswith("Command.collect"):
            obj = self.model_copy()
            if "found_files" in obj.seen_variables:
                del obj.seen_variables["found_files"]
        elif self.function_name.endswith("AppConfig.default_auto_field"):
            obj = self.model_copy()
            if "settings" in obj.seen_variables:
                var = obj.seen_variables["settings"]
                if var and "STATIC_ROOT" in var:
                    obj.seen_variables["settings"]["STATIC_ROOT"] = "<tmpdir>"
        elif self.function_name.endswith("Command.handle"):
            obj = self.model_copy()
            if "destination_path" in obj.seen_variables:
                obj.seen_variables["destination_path"] = "<tmpdir>"
            if "message" in obj.seen_variables:
                var = obj.seen_variables["message"]
                if isinstance(var, list) and len(var) > 2:
                    obj.seen_variables["message"][2] = ":\n\n    <tmpdir>\n\n"
        elif self.function_name.endswith("Field.__deepcopy__"):
            obj = self.model_copy()
            if "memodict" in obj.seen_variables:
                del obj.seen_variables["memodict"]
        else:
            obj = self
        return obj.model_dump(exclude={
            "event_id", "event_type", "line_number", "statement", "excluded",
            "vars_defined", "vars_used",
            "control_dependencies", "inherited_control_dependencies",
        })

class InspectionException(BaseModel):
    stage: str
    type: Optional[str]
    message: Optional[str]
    traceback: Optional[List[str]]

class InspectionResult(BaseModel):
    file: str
    line: int
    expr: List[str]
    value: Optional[List[Any]]
    exception: InspectionException | List[Optional[InspectionException]]