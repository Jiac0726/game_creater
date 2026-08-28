from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.collaboration_models import (
    AuditEvent,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthSession,
    ReviewStatus,
    Team,
    TeamAssetShareRequest,
    TeamComment,
    TeamCommentCreate,
    TeamCreateRequest,
    TeamMember,
    TeamMemberAddRequest,
    TeamMemberPatch,
    TeamReview,
    TeamReviewCreate,
    TeamReviewDecision,
    TeamRole,
    TeamSharedAsset,
    UserPublic,
)
from app.services.asset_library import AssetLibrary, utc_now


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(PermissionError):
    pass


class TeamNotFoundError(KeyError):
    pass


class UserNotFoundError(KeyError):
    pass


class TeamReviewNotFoundError(KeyError):
    pass


class CollaborationService:
    USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
    SESSION_DAYS = 30

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.state_dir = self.workspace.parent / ".game_creater_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "collaboration.db"
        self._init_schema()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS collab_users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_norm TEXT NOT NULL UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collab_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES collab_users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS collab_teams (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(created_by) REFERENCES collab_users(id)
                );
                CREATE TABLE IF NOT EXISTS collab_team_members (
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY(team_id,user_id),
                    FOREIGN KEY(team_id) REFERENCES collab_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES collab_users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS collab_team_assets (
                    team_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    shared_by TEXT NOT NULL,
                    shared_at TEXT NOT NULL,
                    PRIMARY KEY(team_id,asset_id),
                    FOREIGN KEY(team_id) REFERENCES collab_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(shared_by) REFERENCES collab_users(id)
                );
                CREATE TABLE IF NOT EXISTS collab_comments (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES collab_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(author_id) REFERENCES collab_users(id)
                );
                CREATE TABLE IF NOT EXISTS collab_reviews (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    reviewer_id TEXT,
                    status TEXT NOT NULL,
                    request_note TEXT NOT NULL DEFAULT '',
                    decision_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES collab_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(requester_id) REFERENCES collab_users(id),
                    FOREIGN KEY(reviewer_id) REFERENCES collab_users(id)
                );
                CREATE TABLE IF NOT EXISTS collab_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(team_id) REFERENCES collab_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(actor_id) REFERENCES collab_users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_collab_members_user ON collab_team_members(user_id,team_id);
                CREATE INDEX IF NOT EXISTS idx_collab_comments_asset ON collab_comments(team_id,asset_id,created_at);
                CREATE INDEX IF NOT EXISTS idx_collab_reviews_team ON collab_reviews(team_id,updated_at);
                CREATE INDEX IF NOT EXISTS idx_collab_audit_team ON collab_audit(team_id,id);
                """
            )

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_username(cls, username: str) -> tuple[str, str]:
        clean = username.strip()
        if not cls.USERNAME_RE.fullmatch(clean):
            raise ValueError("Username must be 3-32 characters using letters, numbers, _, . or -")
        return clean, clean.lower()

    def register(self, request: AuthRegisterRequest) -> UserPublic:
        username, username_norm = self._normalize_username(request.username)
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(request.password, salt)
        user_id = f"user_{uuid4().hex[:12]}"
        now = utc_now()
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO collab_users(id,username,username_norm,password_salt,password_hash,created_at) VALUES (?,?,?,?,?,?)",
                    (user_id, username, username_norm, salt, password_hash, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists") from exc
        return UserPublic(id=user_id, username=username, created_at=now)

    def login(self, request: AuthLoginRequest) -> AuthSession:
        _, username_norm = self._normalize_username(request.username)
        with self._connect() as db:
            row = db.execute("SELECT * FROM collab_users WHERE username_norm=?", (username_norm,)).fetchone()
        if row is None:
            raise AuthenticationError("Invalid username or password")
        candidate = self._password_hash(request.password, bytes(row["password_salt"]))
        if not hmac.compare_digest(candidate, bytes(row["password_hash"])):
            raise AuthenticationError("Invalid username or password")
        token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.SESSION_DAYS)
        with self._connect() as db:
            db.execute(
                "INSERT INTO collab_sessions(token_hash,user_id,expires_at,created_at) VALUES (?,?,?,?)",
                (token_hash, row["id"], expires.isoformat(), now.isoformat()),
            )
        return AuthSession(
            token=token,
            user=UserPublic(id=row["id"], username=row["username"], created_at=row["created_at"]),
            expires_at=expires.isoformat(),
        )

    def authenticate(self, token: str) -> UserPublic:
        if not token:
            raise AuthenticationError("Missing session token")
        token_hash = self._token_hash(token)
        with self._connect() as db:
            row = db.execute(
                """
                SELECT s.expires_at,u.id,u.username,u.created_at
                FROM collab_sessions s JOIN collab_users u ON u.id=s.user_id
                WHERE s.token_hash=?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            raise AuthenticationError("Invalid session token")
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            with self._connect() as db:
                db.execute("DELETE FROM collab_sessions WHERE token_hash=?", (token_hash,))
            raise AuthenticationError("Session expired")
        return UserPublic(id=row["id"], username=row["username"], created_at=row["created_at"])

    def logout(self, token: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM collab_sessions WHERE token_hash=?", (self._token_hash(token),))

    def create_team(self, actor: UserPublic, request: TeamCreateRequest) -> Team:
        name = request.name.strip()
        if not name:
            raise ValueError("Team name cannot be empty")
        team_id = f"team_{uuid4().hex[:12]}"
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO collab_teams(id,name,description,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (team_id, name, request.description.strip(), actor.id, now, now),
            )
            db.execute(
                "INSERT INTO collab_team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?)",
                (team_id, actor.id, TeamRole.OWNER.value, now),
            )
        self._audit(team_id, actor, "team.create", "team", team_id, {"name": name})
        return self.get_team(actor, team_id)

    def list_teams(self, actor: UserPublic) -> list[Team]:
        with self._connect() as db:
            ids = [
                row["team_id"]
                for row in db.execute(
                    "SELECT team_id FROM collab_team_members WHERE user_id=? ORDER BY joined_at DESC",
                    (actor.id,),
                ).fetchall()
            ]
        return [self.get_team(actor, team_id) for team_id in ids]

    def _role(self, team_id: str, user_id: str) -> TeamRole:
        with self._connect() as db:
            row = db.execute(
                "SELECT role FROM collab_team_members WHERE team_id=? AND user_id=?",
                (team_id, user_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("You are not a member of this team")
        return TeamRole(row["role"])

    def _require(self, team_id: str, actor: UserPublic, allowed: set[TeamRole]) -> TeamRole:
        role = self._role(team_id, actor.id)
        if role not in allowed:
            raise AuthorizationError("Insufficient team permission")
        return role

    def get_team(self, actor: UserPublic, team_id: str) -> Team:
        role = self._role(team_id, actor.id)
        with self._connect() as db:
            row = db.execute("SELECT * FROM collab_teams WHERE id=?", (team_id,)).fetchone()
            if row is None:
                raise TeamNotFoundError(team_id)
            members = db.execute(
                """
                SELECT m.user_id,u.username,m.role,m.joined_at
                FROM collab_team_members m JOIN collab_users u ON u.id=m.user_id
                WHERE m.team_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 WHEN 'editor' THEN 2 WHEN 'reviewer' THEN 3 ELSE 4 END,u.username
                """,
                (team_id,),
            ).fetchall()
            assets = db.execute(
                "SELECT asset_id,shared_by,shared_at FROM collab_team_assets WHERE team_id=? ORDER BY shared_at DESC,asset_id",
                (team_id,),
            ).fetchall()
        return Team(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            current_user_role=role,
            members=[TeamMember(user_id=m["user_id"], username=m["username"], role=TeamRole(m["role"]), joined_at=m["joined_at"]) for m in members],
            assets=[TeamSharedAsset(asset_id=a["asset_id"], shared_by=a["shared_by"], shared_at=a["shared_at"]) for a in assets],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_member(self, actor: UserPublic, team_id: str, request: TeamMemberAddRequest) -> Team:
        actor_role = self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN})
        if request.role == TeamRole.OWNER:
            raise ValueError("Owner role cannot be assigned through member add")
        if actor_role == TeamRole.ADMIN and request.role == TeamRole.ADMIN:
            raise AuthorizationError("Only owner may grant admin role")
        _, username_norm = self._normalize_username(request.username)
        with self._connect() as db:
            user = db.execute("SELECT id,username FROM collab_users WHERE username_norm=?", (username_norm,)).fetchone()
        if user is None:
            raise UserNotFoundError(request.username)
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO collab_team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?) ON CONFLICT(team_id,user_id) DO UPDATE SET role=excluded.role",
                (team_id, user["id"], request.role.value, now),
            )
            db.execute("UPDATE collab_teams SET updated_at=? WHERE id=?", (now, team_id))
        self._audit(team_id, actor, "member.add", "user", user["id"], {"role": request.role.value})
        return self.get_team(actor, team_id)

    def patch_member(self, actor: UserPublic, team_id: str, user_id: str, patch: TeamMemberPatch) -> Team:
        actor_role = self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN})
        target_role = self._role(team_id, user_id)
        if target_role == TeamRole.OWNER or patch.role == TeamRole.OWNER:
            raise ValueError("Owner role cannot be changed through member patch")
        if actor_role == TeamRole.ADMIN and (target_role == TeamRole.ADMIN or patch.role == TeamRole.ADMIN):
            raise AuthorizationError("Only owner may manage admin roles")
        with self._connect() as db:
            db.execute(
                "UPDATE collab_team_members SET role=? WHERE team_id=? AND user_id=?",
                (patch.role.value, team_id, user_id),
            )
            db.execute("UPDATE collab_teams SET updated_at=? WHERE id=?", (utc_now(), team_id))
        self._audit(team_id, actor, "member.role", "user", user_id, {"role": patch.role.value})
        return self.get_team(actor, team_id)

    def remove_member(self, actor: UserPublic, team_id: str, user_id: str) -> Team:
        actor_role = self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN})
        target_role = self._role(team_id, user_id)
        if target_role == TeamRole.OWNER:
            raise ValueError("Team owner cannot be removed")
        if actor_role == TeamRole.ADMIN and target_role == TeamRole.ADMIN:
            raise AuthorizationError("Only owner may remove admins")
        with self._connect() as db:
            db.execute("DELETE FROM collab_team_members WHERE team_id=? AND user_id=?", (team_id, user_id))
            db.execute("UPDATE collab_teams SET updated_at=? WHERE id=?", (utc_now(), team_id))
        self._audit(team_id, actor, "member.remove", "user", user_id, {})
        return self.get_team(actor, team_id)

    def share_assets(self, actor: UserPublic, team_id: str, request: TeamAssetShareRequest) -> Team:
        self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN, TeamRole.EDITOR})
        ids = list(dict.fromkeys(item.strip() for item in request.asset_ids if item.strip()))
        if not ids:
            raise ValueError("At least one asset is required")
        for asset_id in ids:
            self.library.get(asset_id)
        now = utc_now()
        with self._connect() as db:
            for asset_id in ids:
                db.execute(
                    "INSERT OR IGNORE INTO collab_team_assets(team_id,asset_id,shared_by,shared_at) VALUES (?,?,?,?)",
                    (team_id, asset_id, actor.id, now),
                )
            db.execute("UPDATE collab_teams SET updated_at=? WHERE id=?", (now, team_id))
        self._audit(team_id, actor, "asset.share", "asset_set", ",".join(ids), {"count": len(ids)})
        return self.get_team(actor, team_id)

    def unshare_asset(self, actor: UserPublic, team_id: str, asset_id: str) -> Team:
        self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN, TeamRole.EDITOR})
        with self._connect() as db:
            db.execute("DELETE FROM collab_team_assets WHERE team_id=? AND asset_id=?", (team_id, asset_id))
            db.execute("DELETE FROM collab_comments WHERE team_id=? AND asset_id=?", (team_id, asset_id))
            db.execute("DELETE FROM collab_reviews WHERE team_id=? AND asset_id=?", (team_id, asset_id))
            db.execute("UPDATE collab_teams SET updated_at=? WHERE id=?", (utc_now(), team_id))
        self._audit(team_id, actor, "asset.unshare", "asset", asset_id, {})
        return self.get_team(actor, team_id)

    def _require_shared_asset(self, team_id: str, asset_id: str) -> None:
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM collab_team_assets WHERE team_id=? AND asset_id=?", (team_id, asset_id)).fetchone()
        if row is None:
            raise ValueError("Asset is not shared with this team")

    def list_comments(self, actor: UserPublic, team_id: str, asset_id: str) -> list[TeamComment]:
        self._require(team_id, actor, set(TeamRole))
        self._require_shared_asset(team_id, asset_id)
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT c.*,u.username FROM collab_comments c JOIN collab_users u ON u.id=c.author_id
                WHERE c.team_id=? AND c.asset_id=? ORDER BY c.created_at,c.id
                """,
                (team_id, asset_id),
            ).fetchall()
        return [TeamComment(id=r["id"], team_id=r["team_id"], asset_id=r["asset_id"], author_id=r["author_id"], author_username=r["username"], body=r["body"], created_at=r["created_at"]) for r in rows]

    def add_comment(self, actor: UserPublic, team_id: str, asset_id: str, request: TeamCommentCreate) -> TeamComment:
        self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN, TeamRole.EDITOR, TeamRole.REVIEWER})
        self._require_shared_asset(team_id, asset_id)
        body = request.body.strip()
        if not body:
            raise ValueError("Comment cannot be empty")
        comment_id = f"comment_{uuid4().hex[:12]}"
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO collab_comments(id,team_id,asset_id,author_id,body,created_at) VALUES (?,?,?,?,?,?)",
                (comment_id, team_id, asset_id, actor.id, body, now),
            )
        self._audit(team_id, actor, "comment.add", "asset", asset_id, {"comment_id": comment_id})
        return TeamComment(id=comment_id, team_id=team_id, asset_id=asset_id, author_id=actor.id, author_username=actor.username, body=body, created_at=now)

    def create_review(self, actor: UserPublic, team_id: str, request: TeamReviewCreate) -> TeamReview:
        self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN, TeamRole.EDITOR})
        self._require_shared_asset(team_id, request.asset_id)
        review_id = f"review_{uuid4().hex[:12]}"
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO collab_reviews(id,team_id,asset_id,requester_id,status,request_note,decision_note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (review_id, team_id, request.asset_id, actor.id, ReviewStatus.PENDING.value, request.note.strip(), "", now, now),
            )
        self._audit(team_id, actor, "review.request", "review", review_id, {"asset_id": request.asset_id})
        return self.get_review(actor, team_id, review_id)

    def list_reviews(self, actor: UserPublic, team_id: str) -> list[TeamReview]:
        self._require(team_id, actor, set(TeamRole))
        with self._connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM collab_reviews WHERE team_id=? ORDER BY updated_at DESC,id", (team_id,)).fetchall()]
        return [self.get_review(actor, team_id, review_id) for review_id in ids]

    def get_review(self, actor: UserPublic, team_id: str, review_id: str) -> TeamReview:
        self._require(team_id, actor, set(TeamRole))
        with self._connect() as db:
            row = db.execute(
                """
                SELECT r.*,rq.username requester_username,rv.username reviewer_username
                FROM collab_reviews r
                JOIN collab_users rq ON rq.id=r.requester_id
                LEFT JOIN collab_users rv ON rv.id=r.reviewer_id
                WHERE r.team_id=? AND r.id=?
                """,
                (team_id, review_id),
            ).fetchone()
        if row is None:
            raise TeamReviewNotFoundError(review_id)
        return TeamReview(
            id=row["id"], team_id=row["team_id"], asset_id=row["asset_id"],
            requester_id=row["requester_id"], requester_username=row["requester_username"],
            status=ReviewStatus(row["status"]), reviewer_id=row["reviewer_id"], reviewer_username=row["reviewer_username"],
            request_note=row["request_note"], decision_note=row["decision_note"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def decide_review(self, actor: UserPublic, team_id: str, review_id: str, decision: TeamReviewDecision) -> TeamReview:
        self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN, TeamRole.REVIEWER})
        if decision.status == ReviewStatus.PENDING:
            raise ValueError("Review decision must be approved or changes_requested")
        current = self.get_review(actor, team_id, review_id)
        if current.requester_id == actor.id and self._role(team_id, actor.id) != TeamRole.OWNER:
            raise AuthorizationError("Requester cannot decide their own review")
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "UPDATE collab_reviews SET reviewer_id=?,status=?,decision_note=?,updated_at=? WHERE id=? AND team_id=?",
                (actor.id, decision.status.value, decision.note.strip(), now, review_id, team_id),
            )
        self._audit(team_id, actor, "review.decide", "review", review_id, {"status": decision.status.value})
        return self.get_review(actor, team_id, review_id)

    def audit(self, actor: UserPublic, team_id: str, limit: int = 100) -> list[AuditEvent]:
        self._require(team_id, actor, {TeamRole.OWNER, TeamRole.ADMIN})
        limit = max(1, min(int(limit), 500))
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT a.*,u.username FROM collab_audit a JOIN collab_users u ON u.id=a.actor_id
                WHERE a.team_id=? ORDER BY a.id DESC LIMIT ?
                """,
                (team_id, limit),
            ).fetchall()
        return [AuditEvent(id=r["id"], team_id=r["team_id"], actor_id=r["actor_id"], actor_username=r["username"], action=r["action"], target_type=r["target_type"], target_id=r["target_id"], metadata=json.loads(r["metadata_json"] or "{}"), created_at=r["created_at"]) for r in rows]

    def _audit(self, team_id: str, actor: UserPublic, action: str, target_type: str, target_id: str, metadata: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO collab_audit(team_id,actor_id,action,target_type,target_id,metadata_json,created_at) VALUES (?,?,?,?,?,?,?)",
                (team_id, actor.id, action, target_type, target_id, json.dumps(metadata, ensure_ascii=False), utc_now()),
            )
