"""Stage 5 local vision capability.

The package intentionally does not re-export the FastAPI ``router`` object.
Keeping ``app.vision.router`` bound to the actual module avoids shadowing the
submodule and makes normal imports/monkeypatching predictable.
"""
