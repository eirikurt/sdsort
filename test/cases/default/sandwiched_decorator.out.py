from functools import cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic


e2e_secret_path = "/some/secret/path"


e2e_app = FastAPI(
    root_path="/api/e2e",
    openapi_tags=[{"name": "E2E", "description": "Test Automation Service"}],
    docs_url=None,
    redoc_url=None,
)

security = HTTPBasic()


@e2e_app.middleware("http")
async def auth(request: Request, call_next):
    # Allow access if the request is for the OpenAPI spec
    if request.url.path == f"{e2e_app.root_path}{e2e_app.openapi_url}":
        return await call_next(request)

    password = read_e2e_password_from_file()
    credentials = None
    try:
        credentials = await security(request)
    except HTTPException:
        pass
    if (
        credentials is not None
        and password is not None
        and credentials.username == "e2e"
        and credentials.password == password
    ):
        return await call_next(request)

    return HTMLResponse(content="Unauthorized", status_code=401)


@cache
def read_e2e_password_from_file():
    return e2e_secret_path.read_text().strip()
