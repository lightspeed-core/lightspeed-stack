"""Package-shipped data files for Lightspeed Core Stack.

Currently holds ``default_run.yaml``, the built-in baseline Llama Stack
configuration used by unified-mode synthesis (see
``llama_stack_configuration.load_default_baseline``). Making this directory a
package ensures the data file is included in built wheels and resolvable both
in editable installs and from site-packages.
"""
