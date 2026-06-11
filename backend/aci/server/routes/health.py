from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from aci.common.logging_setup import get_logger
from aci.server.dependencies import yield_db_session

logger = get_logger(__name__)
router = APIRouter()


@router.get("", include_in_schema=False)
async def health(db_session: Annotated[Session, Depends(yield_db_session)]) -> bool:
    db_session.execute(text("SELECT 1"))
    return True