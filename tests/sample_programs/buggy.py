from tracer import ExecutionTracer

class SimpleClass:
    def classify(self, x):
        if x >= 0:
            category = "positive"
        else:
            category = "non-positive"
        return category

def initialize_and_use_with_input(x):
    """Version that accepts input for more flexible testing."""
    obj = SimpleClass()
    result = obj.classify(x)
    processed = f"Category: {result.upper()}"
    return processed

def run_tests():
    processed = initialize_and_use_with_input(0)
    assert processed == "Category: NON-POSITIVE", "Failed: zero should be non-positive"

# Main guard to run tests
if __name__ == "__main__":
    print("Running tests...")
    tracer = ExecutionTracer(output_file="sample_programs/buggy.jsonl")
    tracer.start_tracing()
    try:
        run_tests()
        print("All tests passed...")
    except:
        pass
    finally:
        tracer.stop_tracing()
        tracer.save_trace()
