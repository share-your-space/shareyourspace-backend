from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple
import logging
import datetime

from app import models, schemas, crud
from app.crud import crud_user_profile
from app.crud import crud_interest
from app.schemas.matching import MatchResult
from app.db.session import get_db
from app.security import get_current_active_user
from app.utils import storage

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Scoring Constants (Keep simple for MVP) ---
VECTOR_WEIGHT = 0.7
STRUCTURED_WEIGHT = 0.3
SHARED_SKILL_SCORE = 5
SHARED_INDUSTRY_SCORE = 3
INTEREST_BOOST_SCORE = 25 # A significant boost for expressing interest


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
    Excludes users already connected to the current user.
    """
    logger.info(f"Discover endpoint called by user_id={current_user.id}")

    if not current_user.profile:
        profile = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
        if not profile:
            logger.error(f"User {current_user.id} has no profile object. Cannot perform discovery.")
            return [MatchResult(message="Your profile is incomplete. Please fill out your profile to discover other users.")]
        current_user.profile = profile
        
    if current_user.profile.profile_vector is None:
        logger.warning(f"User {current_user.id} profile has no embedding vector.")
        return [MatchResult(message="Your profile is missing key information. Please complete your profile to enable discovery.")]
        
    if not current_user.space_id and not current_user.managed_space:
        logger.warning(f"User {current_user.id} is not assigned to a space and does not manage one. Returning empty list for discovery.")
        return []

    # Get IDs of users already connected to the current user
    connected_connections = await crud.crud_connection.get_accepted_connections_for_user(db=db, user_id=current_user.id)
    exclude_user_ids = [conn.requester_id if conn.recipient_id == current_user.id else conn.recipient_id for conn in connected_connections]
    logger.info(f"User {current_user.id} is already connected with user IDs: {exclude_user_ids}")

    # --- Interest Boost Logic ---
    interested_user_ids = set()
    if current_user.role == 'CORP_ADMIN' and current_user.managed_space:
        interests = await crud_interest.interest.get_interests_for_space(db, space_id=current_user.managed_space.id)
        interested_user_ids = {interest.user_id for interest in interests if interest.status == 'PENDING'}
        logger.info(f"Corp Admin {current_user.id} is discovering. Found {len(interested_user_ids)} users interested in their space.")
    # --- End Interest Boost ---

    logger.info(f"ROUTER_MATCHING: Calling find_similar_users for user {current_user.id} in space {current_user.space_id or current_user.managed_space.id}")
    similar_users_with_distance = await crud_user_profile.find_similar_users(
        db=db, requesting_user=current_user, limit=20, exclude_user_ids=exclude_user_ids
    )
    logger.info(f"ROUTER_MATCHING: find_similar_users returned for user {current_user.id}. Count: {len(similar_users_with_distance)}")
    if similar_users_with_distance:
        # Log details of what was returned, e.g., user IDs and distances
        returned_data_log = [(p.user_id, d) for p, d in similar_users_with_distance]
        logger.info(f"ROUTER_MATCHING: Data from find_similar_users: {returned_data_log}")
    else:
        logger.info(f"ROUTER_MATCHING: find_similar_users returned an empty list.")
    
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
        
        # Apply interest boost
        if candidate_profile.user_id in interested_user_ids:
            final_score += INTEREST_BOOST_SCORE
            match_reasons.append("Expressed interest in your space")
        
        profile_schema = schemas.UserProfile.model_validate(candidate_profile)

        # Manually set the full_name from the eagerly loaded user relationship
        if candidate_profile.user:
            profile_schema.full_name = candidate_profile.user.full_name

        # --- Generate Signed URL ---
        signed_url = None
        if candidate_profile.profile_picture_url:
            signed_url = storage.generate_gcs_signed_url(candidate_profile.profile_picture_url)
            
        profile_schema.profile_picture_signed_url = signed_url
        
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
