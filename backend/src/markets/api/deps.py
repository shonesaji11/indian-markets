from fastapi import Request

from markets.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container
