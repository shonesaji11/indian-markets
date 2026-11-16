"""Use cases that wire ports together: provider -> storage, storage -> engine -> storage.

Pipelines depend only on the protocols in markets.core.ports and on the engine
registry, never on concrete adapters. Concrete wiring happens in markets.bootstrap.
"""
