from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.collaboration_models import (
    AuditEvent,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthSession,
    Team,
    TeamAssetShareRequest,
    TeamComment,
    TeamCommentCreate,
    TeamCreateRequest,
    TeamMemberAddRequest,
    TeamMemberPatch,
    TeamReview,
    TeamReviewCreate,
    TeamReviewDecision,
    UserPublic,
)
from app.services.asset_library import LibraryAssetNotFoundError
from app.services.collaboration import (
    AuthenticationError,
    AuthorizationError,
    CollaborationService,
    TeamReviewNotFoundError,
    UserNotFoundError,
)


def build_collaboration_router(workspace) -> APIRouter:
    router = APIRouter(prefix="/collab", tags=["collaboration"])
    service = CollaborationService(workspace)

    def bearer_token(authorization: str | None) -> str:
        value = (authorization or "").strip()
        if not value.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Bearer session token required")
        token = value[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Bearer session token required")
        return token

    def actor(authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> UserPublic:
        try:
            return service.authenticate(bearer_token(authorization))
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def guarded(call):
        try:
            return call()
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (UserNotFoundError, TeamReviewNotFoundError, LibraryAssetNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/auth/register", response_model=UserPublic)
    def register(request: AuthRegisterRequest) -> UserPublic:
        try:
            return service.register(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/auth/login", response_model=AuthSession)
    def login(request: AuthLoginRequest) -> AuthSession:
        try:
            return service.login(request)
        except (AuthenticationError, ValueError) as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @router.post("/auth/logout", status_code=204)
    def logout(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        current: UserPublic = Depends(actor),
    ) -> Response:
        del current
        service.logout(bearer_token(authorization))
        return Response(status_code=204)

    @router.get("/me", response_model=UserPublic)
    def me(current: UserPublic = Depends(actor)) -> UserPublic:
        return current

    @router.get("/teams", response_model=list[Team])
    def list_teams(current: UserPublic = Depends(actor)) -> list[Team]:
        return service.list_teams(current)

    @router.post("/teams", response_model=Team)
    def create_team(request: TeamCreateRequest, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.create_team(current, request))

    @router.get("/teams/{team_id}", response_model=Team)
    def get_team(team_id: str, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.get_team(current, team_id))

    @router.post("/teams/{team_id}/members", response_model=Team)
    def add_member(team_id: str, request: TeamMemberAddRequest, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.add_member(current, team_id, request))

    @router.patch("/teams/{team_id}/members/{user_id}", response_model=Team)
    def patch_member(team_id: str, user_id: str, patch: TeamMemberPatch, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.patch_member(current, team_id, user_id, patch))

    @router.delete("/teams/{team_id}/members/{user_id}", response_model=Team)
    def remove_member(team_id: str, user_id: str, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.remove_member(current, team_id, user_id))

    @router.post("/teams/{team_id}/assets", response_model=Team)
    def share_assets(team_id: str, request: TeamAssetShareRequest, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.share_assets(current, team_id, request))

    @router.delete("/teams/{team_id}/assets/{asset_id}", response_model=Team)
    def unshare_asset(team_id: str, asset_id: str, current: UserPublic = Depends(actor)) -> Team:
        return guarded(lambda: service.unshare_asset(current, team_id, asset_id))

    @router.get("/teams/{team_id}/assets/{asset_id}/comments", response_model=list[TeamComment])
    def list_comments(team_id: str, asset_id: str, current: UserPublic = Depends(actor)) -> list[TeamComment]:
        return guarded(lambda: service.list_comments(current, team_id, asset_id))

    @router.post("/teams/{team_id}/assets/{asset_id}/comments", response_model=TeamComment)
    def add_comment(team_id: str, asset_id: str, request: TeamCommentCreate, current: UserPublic = Depends(actor)) -> TeamComment:
        return guarded(lambda: service.add_comment(current, team_id, asset_id, request))

    @router.get("/teams/{team_id}/reviews", response_model=list[TeamReview])
    def list_reviews(team_id: str, current: UserPublic = Depends(actor)) -> list[TeamReview]:
        return guarded(lambda: service.list_reviews(current, team_id))

    @router.post("/teams/{team_id}/reviews", response_model=TeamReview)
    def create_review(team_id: str, request: TeamReviewCreate, current: UserPublic = Depends(actor)) -> TeamReview:
        return guarded(lambda: service.create_review(current, team_id, request))

    @router.patch("/teams/{team_id}/reviews/{review_id}", response_model=TeamReview)
    def decide_review(team_id: str, review_id: str, decision: TeamReviewDecision, current: UserPublic = Depends(actor)) -> TeamReview:
        return guarded(lambda: service.decide_review(current, team_id, review_id, decision))

    @router.get("/teams/{team_id}/audit", response_model=list[AuditEvent])
    def audit(team_id: str, limit: int = 100, current: UserPublic = Depends(actor)) -> list[AuditEvent]:
        return guarded(lambda: service.audit(current, team_id, limit))

    return router
