from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.db.redis import get_redis
from app.memory.user_preferences import UserPreferenceStore
from app.memory.attack_knowledge import AttackKnowledgeBase
from app.memory.fix_patterns import FixPatternStore

router = APIRouter(prefix="/api/v1", tags=["preferences"])


class PreferencesResponse(BaseModel):
    preferences: dict
    stats: dict


class PreferencesUpdate(BaseModel):
    preferred_language: str | None = None
    preferred_framework: str | None = None


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(user=Depends(get_current_user)):
    store = UserPreferenceStore(redis_client=get_redis())
    prefs = await store.get_preferences(str(user.id))

    attack_kb = AttackKnowledgeBase()
    fix_store = FixPatternStore()

    attack_count = 0
    fix_count = 0
    if attack_kb._available:
        try:
            attack_count = attack_kb.collection.count()
        except Exception:
            pass
    if fix_store._available:
        try:
            fix_count = fix_store.collection.count()
        except Exception:
            pass

    return PreferencesResponse(
        preferences=prefs,
        stats={
            "attack_experiences": attack_count,
            "fix_patterns": fix_count,
        },
    )


@router.post("/preferences")
async def update_preferences(
    body: PreferencesUpdate,
    user=Depends(get_current_user),
):
    store = UserPreferenceStore(redis_client=get_redis())
    updates = {}
    if body.preferred_language is not None:
        updates["language"] = body.preferred_language
    if body.preferred_framework is not None:
        updates["framework"] = body.preferred_framework
    if updates:
        await store.update_from_request(str(user.id), updates)
    return {"ok": True}


@router.delete("/preferences")
async def clear_preferences(user=Depends(get_current_user)):
    redis = get_redis()
    key = f"user_pref:{user.id}"
    try:
        await redis.delete(key)
    except Exception:
        pass
    return {"ok": True}
