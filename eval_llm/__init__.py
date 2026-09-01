"""Real-LLM evaluation tooling for the harness.

Deliberately separate from ``src/``: this is eval/test infrastructure, not a harness
layer, so it stays out of the coverage ``source`` gate. The pytest suite lives in
``tests/test_real_llm.py`` and only runs when ``RUN_REAL_LLM=1``.
"""
