from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from app.collaboration_models import (
    AuthLoginRequest,
    AuthRegisterRequest,
    ReviewStatus,
    TeamAssetShareRequest,
    TeamCommentCreate,
    TeamCreateRequest,
    TeamMemberAddRequest,
    TeamReviewCreate,
    TeamReviewDecision,
    TeamRole,
)
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.collaboration import AuthenticationError, AuthorizationError, CollaborationService
from app.services.pipeline import AssetSplitPipeline


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    workspace = tmp_path / "workspace"
    workflow = AssetLibraryWorkflowService(workspace, AssetSplitPipeline(workspace))
    collab = CollaborationService(workspace)
    return workflow, collab


def _user(collab: CollaborationService, username: str):
    password = f"{username}-password"
    collab.register(AuthRegisterRequest(username=username, password=password))
    session = collab.login(AuthLoginRequest(username=username, password=password))
    return session.user, session.token


def _asset(workflow: AssetLibraryWorkflowService, tmp_path: Path, name: str):
    path = tmp_path / f"{name}.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path)
    return workflow.import_image(path, name=name, category="prop")


def test_auth_session_and_team_roles_enforce_permissions(tmp_path: Path, monkeypatch) -> None:
    workflow, collab = _setup(tmp_path, monkeypatch)
    owner, owner_token = _user(collab, "owneruser")
    editor, _ = _user(collab, "editoruser")
    reviewer, _ = _user(collab, "revieweruser")
    viewer, _ = _user(collab, "vieweruser")

    assert collab.authenticate(owner_token).id == owner.id
    with pytest.raises(AuthenticationError):
        collab.authenticate("not-a-real-token")

    team = collab.create_team(owner, TeamCreateRequest(name="Art Team"))
    assert team.current_user_role == TeamRole.OWNER
    collab.add_member(owner, team.id, TeamMemberAddRequest(username=editor.username, role=TeamRole.EDITOR))
    collab.add_member(owner, team.id, TeamMemberAddRequest(username=reviewer.username, role=TeamRole.REVIEWER))
    collab.add_member(owner, team.id, TeamMemberAddRequest(username=viewer.username, role=TeamRole.VIEWER))

    asset = _asset(workflow, tmp_path, "tree")
    with pytest.raises(AuthorizationError):
        collab.share_assets(viewer, team.id, TeamAssetShareRequest(asset_ids=[asset.id]))
    team = collab.share_assets(editor, team.id, TeamAssetShareRequest(asset_ids=[asset.id]))
    assert [item.asset_id for item in team.assets] == [asset.id]


def test_comments_review_flow_and_audit(tmp_path: Path, monkeypatch) -> None:
    workflow, collab = _setup(tmp_path, monkeypatch)
    owner, _ = _user(collab, "teamowner")
    editor, _ = _user(collab, "teameditor")
    reviewer, _ = _user(collab, "teamreviewer")
    team = collab.create_team(owner, TeamCreateRequest(name="Review Team"))
    collab.add_member(owner, team.id, TeamMemberAddRequest(username=editor.username, role=TeamRole.EDITOR))
    collab.add_member(owner, team.id, TeamMemberAddRequest(username=reviewer.username, role=TeamRole.REVIEWER))
    asset = _asset(workflow, tmp_path, "house")
    collab.share_assets(editor, team.id, TeamAssetShareRequest(asset_ids=[asset.id]))

    comment = collab.add_comment(reviewer, team.id, asset.id, TeamCommentCreate(body="Edge cleanup looks good."))
    assert comment.author_id == reviewer.id
    assert len(collab.list_comments(editor, team.id, asset.id)) == 1

    review = collab.create_review(editor, team.id, TeamReviewCreate(asset_id=asset.id, note="Ready for review"))
    assert review.status == ReviewStatus.PENDING
    with pytest.raises(AuthorizationError, match="own review"):
        collab.decide_review(editor, team.id, review.id, TeamReviewDecision(status=ReviewStatus.APPROVED))
    approved = collab.decide_review(reviewer, team.id, review.id, TeamReviewDecision(status=ReviewStatus.APPROVED, note="Approved"))
    assert approved.status == ReviewStatus.APPROVED
    assert approved.reviewer_id == reviewer.id

    events = collab.audit(owner, team.id)
    actions = {event.action for event in events}
    assert {"team.create", "member.add", "asset.share", "comment.add", "review.request", "review.decide"}.issubset(actions)


def test_logout_revokes_session(tmp_path: Path, monkeypatch) -> None:
    _, collab = _setup(tmp_path, monkeypatch)
    user, token = _user(collab, "logoutuser")
    assert collab.authenticate(token).id == user.id
    collab.logout(token)
    with pytest.raises(AuthenticationError):
        collab.authenticate(token)
