from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from tracer.serializer import deserialize

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

    def dump(self):
        return self.model_dump(exclude={
            "event_id", "line_number", "excluded",
        })

    def deserialized(self):
        return self

class FunctionEvent(Event):
    caller_name: str
    parameters: Dict[str, Any]
    parameter_sources: Dict
    inherited_control_dependencies: List[int]

    def deserialized(self):
        self.parameters = {k: deserialize(v) for k, v in self.parameters.items()}
        return self
    
    def dump(self):
        return self.model_dump(exclude={
            "event_id", "line_number", "excluded",
            "inherited_control_dependencies"
        })

class ReturnEvent(Event):
    vars_used: List[str]
    caller_name: str
    return_value: Any
    
    def deserialized(self):
        self.return_value = deserialize(self.return_value)
        return self

class ExceptionEvent(Event):
    exception_type: str
    exception_value: str
    vars_used: Optional[List[str]] = None

class LineEvent(Event):
    vars_defined: List[str]
    vars_used: List[str]
    control_dependencies: List[int]
    inherited_control_dependencies: List[int]
    seen_variables: Dict[str, Any]

    def deserialized(self):
        self.seen_variables = {k: deserialize(v) for k, v in self.seen_variables.items()}
        return self

    def dump(self):
        return self.model_dump(exclude={
            "event_id", "line_number", "excluded",
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
    expr: str
    value: Optional[Any]
    exception: Optional[InspectionException]