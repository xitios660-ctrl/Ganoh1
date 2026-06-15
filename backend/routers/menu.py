"""Menu and Adicionais Routes — DEPRECATED.

All previous endpoints in this file are now duplicated and superseded by the
ones declared directly in `server.py` (which is registered first and wins
routing). Keeping this file as an empty router prevents an import error in
`server.py` (`api_router.include_router(menu.router)`) without re-adding the
dead routes.

If you ever move menu logic out of `server.py`, add the endpoints back here
and DELETE the duplicates in `server.py` first.
"""
from fastapi import APIRouter
import logging

router = APIRouter(tags=["Menu"])
logger = logging.getLogger(__name__)

# Will be set by main app (kept for backward compat with set_dependencies imports)
db = None
verify_gestor = None


def set_dependencies(database, gestor_verifier=None):
    global db, verify_gestor
    db = database
    verify_gestor = gestor_verifier
