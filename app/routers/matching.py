from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple
import logging

from app import models, schemas, crud
from app.crud import crud_user_profile
from app.schemas.matching import MatchResult
from app.db.session import get_db
from app.security import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Scoring Constants (Keep simple for MVP) ---
VECTOR_WEIGHT = 0.7
STRUCTURED_WEIGHT = 0.3
SHARED_SKILL_SCORE = 5
SHARED_INDUSTRY_SCORE = 3


def calculate_structured_score(
    requesting_profile: models.UserProfile,
    candidate_profile: models.UserProfile
) -> Tuple[int, List[str]]:
    """Calculates score based on structured data overlaps and returns reasons."""
    score = 0
    reasons = []
    
    req_skills = set(requesting_profile.skills_expertise or [])
    cand_skills = set(candidate_profile.skills_expertise or [])
    shared_skills = req_skills.intersection(cand_skills)
    if shared_skills:
        score += len(shared_skills) * SHARED_SKILL_SCORE
        reasons.extend([f"Shared Skill: {s}" for s in shared_skills])
        
    req_industries = set(requesting_profile.industry_focus or [])
    cand_industries = set(candidate_profile.industry_focus or [])
    shared_industries = req_industries.intersection(cand_industries)
    if shared_industries:
        score += len(shared_industries) * SHARED_INDUSTRY_SCORE
        reasons.extend([f"Shared Industry: {i}" for i in shared_industries])
        
    # Add more scoring logic here if needed (e.g., collaboration preferences)
    
    return score, reasons


@router.get("/discover", response_model=List[MatchResult])
async def discover_similar_users(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> List[MatchResult]:
    """
    Discover users with similar profiles within the same space.
    Calculates a combined score based on vector similarity and structured data.
    Returns a ranked list with match reasons.
    """
    logger.info(f"Discover endpoint called by user_id={current_user.id}")

    if not current_user.profile:
        profile = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
        if not profile:
             logger.error(f"User {current_user.id} has no profile object. Cannot perform discovery.")
             raise HTTPException(status_code=404, detail="User profile not found. Please complete your profile.")
        current_user.profile = profile
        
    if current_user.profile.profile_vector is None:
        logger.warning(f"User {current_user.id} profile has no embedding vector.")
        raise HTTPException(status_code=400, detail="Profile embedding not generated yet. Try updating your profile.")
        
    if current_user.space_id is None:
        logger.warning(f"User {current_user.id} is not assigned to a space.")
        raise HTTPException(status_code=400, detail="User not assigned to a space. Cannot discover connections.")

    similar_users_with_distance = await crud_user_profile.find_similar_users(
        db=db, requesting_user=current_user, limit=20
    )
    
    if not similar_users_with_distance:
        logger.info(f"No initial similar users found for user_id={current_user.id}")
        return []

    results = []
    requesting_profile = current_user.profile

    for candidate_profile, distance in similar_users_with_distance:
        vector_similarity_score = max(0.0, 1.0 - float(distance)) 
        match_reasons = ["Similar Profile Vector"]
        
        structured_score_raw, structured_reasons = calculate_structured_score(
            requesting_profile, candidate_profile
        )
        match_reasons.extend(structured_reasons)
        
        final_score = (VECTOR_WEIGHT * vector_similarity_score * 10) + (STRUCTURED_WEIGHT * structured_score_raw)
        
        profile_schema = schemas.UserProfile.model_validate(candidate_profile)

        results.append(MatchResult(
            profile=profile_schema,
            score=final_score,
            reasons=match_reasons
        ))
        logger.debug(f"User {candidate_profile.user_id}: Dist={distance:.4f}, VecScore={vector_similarity_score:.4f}, StructScore={structured_score_raw}, Final={final_score:.4f}, Reasons={match_reasons}")

    results.sort(key=lambda x: x.score, reverse=True)
    
    final_results = results[:10]
    
    logger.info(f"Returning {len(final_results)} refined matches for user_id={current_user.id}")
    return final_results
