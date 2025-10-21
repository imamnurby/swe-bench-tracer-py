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
    
    @staticmethod
    def from_dict(data):
        event_type = data['event_type']
        if event_type == 'Function':
            event = FunctionEvent(**data)
            event.parameters = {k: deserialize(v) for k, v in event.parameters.items()}
            return event
        elif event_type == 'Return':
            event = ReturnEvent(**data)
            event.return_value = deserialize(event.return_value)
            return event
        elif event_type == 'Exception':
            return ExceptionEvent(**data)
        elif event_type == 'Line':
            event = LineEvent(**data)
            event.seen_variables = {k: deserialize(v) for k, v in event.seen_variables.items()}
            return event
        else:
            raise ValueError(f"Unknown event type: {event_type}")

class FunctionEvent(Event):
    caller_name: str
    parameters: Dict[str, Any]
    parameter_sources: Dict
    inherited_control_dependencies: List[int]

class ReturnEvent(Event):
    vars_used: List[str]
    caller_name: str
    return_value: Any

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
