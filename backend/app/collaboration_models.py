from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class UserPublic(BaseModel):
    id: str
    username: str
    created_at: str


class AuthRegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=256)


class AuthLoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=256)


class AuthSession(BaseModel):
    token: str
    user: UserPublic
    expires_at: str


class TeamCreateRequest(BaseModel):
    name: str
    description: str = ""


class TeamMemberAddRequest(BaseModel):
    username: str
    role: TeamRole = TeamRole.VIEWER


class TeamMemberPatch(BaseModel):
    role: TeamRole


class TeamMember(BaseModel):
    user_id: str
    username: str
    role: TeamRole
    joined_at: str


class TeamAssetShareRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=5000)


class TeamSharedAsset(BaseModel):
    asset_id: str
    shared_by: str
    shared_at: str


class Team(BaseModel):
    id: str
    name: str
    description: str = ""
    current_user_role: TeamRole
    members: list[TeamMember] = Field(default_factory=list)
    assets: list[TeamSharedAsset] = Field(default_factory=list)
    created_at: str
    updated_at: str


class TeamCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TeamComment(BaseModel):
    id: str
    team_id: str
    asset_id: str
    author_id: str
    author_username: str
    body: str
    created_at: str


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class TeamReviewCreate(BaseModel):
    asset_id: str
    note: str = Field(default="", max_length=4000)


class TeamReviewDecision(BaseModel):
    status: ReviewStatus
    note: str = Field(default="", max_length=4000)


class TeamReview(BaseModel):
    id: str
    team_id: str
    asset_id: str
    requester_id: str
    requester_username: str
    status: ReviewStatus
    reviewer_id: str | None = None
    reviewer_username: str | None = None
    request_note: str = ""
    decision_note: str = ""
    created_at: str
    updated_at: str


class AuditEvent(BaseModel):
    id: int
    team_id: str
    actor_id: str
    actor_username: str
    action: str
    target_type: str
    target_id: str
    metadata: dict = Field(default_factory=dict)
    created_at: str
