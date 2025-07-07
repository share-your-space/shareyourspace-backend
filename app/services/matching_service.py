import logging
from typing import List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.utils import storage

logger = logging.getLogger(__name__)

# --- Scoring Constants ---
VECTOR_WEIGHT = 0.7
STRUCTURED_WEIGHT = 0.3
SHARED_SKILL_SCORE = 5
SHARED_INDUSTRY_SCORE = 3
INTEREST_BOOST_SCORE = 25

def _calculate_structured_score(
    requesting_profile: models.UserProfile, candidate_profile: models.UserProfile
) -> Tuple[int, List[str]]:
    """Calculates score based on structured data overlaps and returns reasons."""
    score = 0
    reasons = []

    req_skills = set(requesting_profile.skills_expertise or [])
    cand_skills = set(candidate_profile.skills_expertise or [])
    if shared_skills := req_skills.intersection(cand_skills):
        score += len(shared_skills) * SHARED_SKILL_SCORE
        reasons.extend([f"Shared Skill: {s}" for s in shared_skills])

    req_industries = set(requesting_profile.industry_focus or [])
    cand_industries = set(candidate_profile.industry_focus or [])
    if shared_industries := req_industries.intersection(cand_industries):
        score += len(shared_industries) * SHARED_INDUSTRY_SCORE
        reasons.extend([f"Shared Industry: {i}" for i in shared_industries])

    return score, reasons

async def discover_users(db: AsyncSession, *, current_user: models.User) -> List[schemas.matching.MatchResult]:
    # TODO: This feature is temporarily disabled pending rework of the vector search.
    return []
    
    if not current_user.profile:
        return [schemas.matching.MatchResult(message="Please complete your profile to discover others.")]

    if not current_user.space_id and not current_user.managed_space:
        return []

    connected_users = await crud.crud_connection.get_accepted_connections_for_user(db, user_id=current_user.id)
    exclude_user_ids = {conn.requester_id if conn.recipient_id == current_user.id else conn.recipient_id for conn in connected_users}

    interested_user_ids = set()
    if current_user.role == 'CORP_ADMIN' and current_user.company and current_user.company.spaces:
        for space in current_user.company.spaces:
            interests = await crud.crud_interest.interest.get_interests_for_space(db, space_id=space.id)
            for interest in interests:
                if interest.status == 'PENDING':
                    interested_user_ids.add(interest.user_id)

    similar_users = await crud.crud_user_profile.find_similar_users(
        db, requesting_user=current_user, limit=20, exclude_user_ids=list(exclude_user_ids)
    )

    results = []
    for candidate_profile, distance in similar_users:
        vector_score = max(0.0, 1.0 - float(distance))
        structured_score, reasons = _calculate_structured_score(current_user.profile, candidate_profile)
        
        final_score = (VECTOR_WEIGHT * vector_score * 10) + (STRUCTURED_WEIGHT * structured_score)
        if candidate_profile.user_id in interested_user_ids:
            final_score += INTEREST_BOOST_SCORE
            reasons.append("Expressed interest in your space")

        profile_schema = schemas.UserProfile.model_validate(candidate_profile)
        if candidate_profile.user:
            profile_schema.full_name = candidate_profile.user.full_name
        if candidate_profile.profile_picture_url:
            profile_schema.profile_picture_signed_url = storage.generate_gcs_signed_url(candidate_profile.profile_picture_url)

        results.append(schemas.matching.MatchResult(
            profile=profile_schema,
            score=final_score,
            reasons=["Similar Profile"] + reasons
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:10] 