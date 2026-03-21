from fastapi import APIRouter, Depends
from app.database import get_db
from app.dependencies import require_role

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/")
async def list_templates(
    current_user: dict = Depends(require_role("viewer")),
    db=Depends(get_db),
):
    cursor = db.templates.find({}, {"_id": 0}).sort("name", 1)
    return [doc async for doc in cursor]


@router.post("/sync", status_code=202)
async def sync_templates(
    current_user: dict = Depends(require_role("admin")),
):
    from app.workers.template_sync import sync_templates_task
    sync_templates_task.delay()
    return {"message": "Template sync queued"}
