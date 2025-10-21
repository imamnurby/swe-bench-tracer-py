from setuptools import setup, find_packages

setup(
    name="py-tracer",
    version="0.1.0",
    packages=find_packages(include=["tracer", "tracer.*", "tracer_plugin", "tracer_plugin.*"]),
    install_requires=[
        "jsonpickle",
    ],
    extras_require={
        "all": [
            "pytest",
            "pydantic",
            "numpy",
            "pandas",
        ],
    },
    entry_points={
        "pytest11": [
            "tracer_plugin = tracer_plugin.pytest_plugin",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)