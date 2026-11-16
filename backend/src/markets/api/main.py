"""ASGI entry point: `uvicorn markets.api.main:app`."""

from markets.api.app import create_app

app = create_app()
