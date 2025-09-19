class SimpleClass:
    def classify(self, x):
        if x > 0:
            category = "positive"
        else:
            category = "non-positive"
        return category

def test_class_method():
    obj = SimpleClass()
    return obj.classify(5)


def initialize_and_use():
    """Initialize object, call method, and perform operation on output."""
    obj = SimpleClass()                  # Initialize object
    result = obj.classify(-3)            # Call method
    processed = f"Category: {result.upper()}"  # Operation: uppercase + formatting
    return processed

def initialize_and_use_with_input(x):
    """Version that accepts input for more flexible testing."""
    obj = SimpleClass()
    result = obj.classify(x)
    processed = f"Category: {result.upper()}"
    return processed

def run_tests():
    assert initialize_and_use_with_input(7) == "Category: POSITIVE", "Failed: should be 'Category: POSITIVE'"
    assert initialize_and_use_with_input(-5) == "Category: NON-POSITIVE", "Failed: should be 'Category: NON-POSITIVE'"
    assert initialize_and_use_with_input(0) == "Category: NON-POSITIVE", "Failed: zero should be non-positive"

# Main guard to run tests
if __name__ == "__main__":
    print("Running tests...")
    run_tests()
    print("All tests passed...")
