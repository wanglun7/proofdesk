from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from api.kb import router as kb_router
from api.questionnaire import router as questionnaire_router
from api.export import router as export_router

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


app.include_router(kb_router, prefix="/api/kb", tags=["kb"])
app.include_router(questionnaire_router, prefix="/api/questionnaire", tags=["questionnaire"])
app.include_router(export_router, prefix="/api", tags=["export"])
