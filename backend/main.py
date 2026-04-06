from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from api.kb import router as kb_router
from api.questionnaire import router as questionnaire_router
from api.export import router as export_router
from api.projects import router as projects_router
from api.auth import router as auth_router
from api.library import router as library_router
from api.wecom import router as wecom_router
from api.deps import get_current_user
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Proofdesk")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()


# Public route — no auth required
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(wecom_router, prefix="/api/wecom", tags=["wecom"])

# Protected routes
_auth = [Depends(get_current_user)]
app.include_router(projects_router, prefix="/api/projects", tags=["projects"], dependencies=_auth)
app.include_router(kb_router, prefix="/api/kb", tags=["kb"], dependencies=_auth)
app.include_router(questionnaire_router, prefix="/api/questionnaire", tags=["questionnaire"], dependencies=_auth)
app.include_router(export_router, prefix="/api", tags=["export"], dependencies=_auth)
app.include_router(library_router, prefix="/api/library", tags=["library"], dependencies=_auth)

