from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.asset_library_models import AssetRelationType, AssetReviewState, LibraryAssetVersion
from app.asset_workflow_maintenance_models import (
    ActivateAssetVersionResult,
    BatchAssetEditItem,
    BatchAssetEditRequest,
    BatchAssetEditResult,
    PackPreflightIssue,
    PackPreflightRequest,
    PackPreflightResult,
    ReparentAssetsRequest,
    ReparentAssetsResult,
)
from app.services.asset_library import AssetLibrary, LibraryAssetNotFoundError, utc_now
from app.services.asset_library_workflow import AssetLibraryWorkflowService
from app.services.pipeline import AssetSplitPipeline


class AssetLibraryMaintenanceService:
    def __init__(self, workspace: str | Path, pipeline: AssetSplitPipeline) -> None:
        self.workspace = Path(workspace)
        self.library = AssetLibrary(self.workspace)
        self.workflow = AssetLibraryWorkflowService(self.workspace, pipeline)

    def activate_version(self, asset_id: str, version: int) -> ActivateAssetVersionResult:
        asset = self.library.get(asset_id)
        versions = {item.version: item for item in self.library.list_versions(asset_id)}
        selected = versions.get(int(version))
        if selected is None:
            raise ValueError(f"Asset version {version} does not exist")

        image_path = self.workspace / selected.image_path
        if not image_path.is_file():
            raise ValueError(f"Version image is missing: {selected.image_path}")
        with Image.open(image_path) as image:
            width, height = image.size

        if selected.mask_path and not (self.workspace / selected.mask_path).is_file():
            raise ValueError(f"Version mask is missing: {selected.mask_path}")
        if selected.alpha_path and not (self.workspace / selected.alpha_path).is_file():
            raise ValueError(f"Version alpha is missing: {selected.alpha_path}")

        with self.library._connect() as db:
            db.execute(
                """
                UPDATE assets
                SET active_version=?, image_path=?, mask_path=?, alpha_path=?,
                    width=?, height=?, updated_at=?
                WHERE id=?
                """,
                (
                    selected.version,
                    selected.image_path,
                    selected.mask_path or asset.mask_path,
                    selected.alpha_path or asset.alpha_path,
                    int(width),
                    int(height),
                    utc_now(),
                    asset_id,
                ),
            )
        return ActivateAssetVersionResult(asset=self.library.get(asset_id), version=selected)

    def bulk_edit(self, request: BatchAssetEditRequest) -> BatchAssetEditResult:
        seen: set[str] = set()
        items: list[BatchAssetEditItem] = []
        for asset_id in request.asset_ids:
            if asset_id in seen:
                continue
            seen.add(asset_id)
            try:
                result = self.workflow.edit(asset_id, request.edit)
                items.append(BatchAssetEditItem(asset_id=asset_id, ok=True, version=result.version))
            except Exception as exc:
                items.append(BatchAssetEditItem(asset_id=asset_id, ok=False, error=str(exc)))
                if request.stop_on_error:
                    break
        succeeded = sum(1 for item in items if item.ok)
        return BatchAssetEditResult(items=items, succeeded=succeeded, failed=len(items) - succeeded)

    def reparent(self, parent_asset_id: str, request: ReparentAssetsRequest) -> ReparentAssetsResult:
        self.library.get(parent_asset_id)
        child_ids = list(dict.fromkeys(request.child_asset_ids))
        if parent_asset_id in child_ids:
            raise ValueError("An asset cannot be its own child")

        for child_id in child_ids:
            self.library.get(child_id)
            if self._is_descendant(child_id, parent_asset_id):
                raise ValueError(
                    f"Hierarchy cycle rejected: {parent_asset_id} is already below {child_id}"
                )

        removed = 0
        with self.library._connect() as db:
            if request.remove_existing_parents:
                for child_id in child_ids:
                    rows = db.execute(
                        """
                        SELECT source_asset_id FROM asset_relations
                        WHERE target_asset_id=? AND relation_type=?
                        """,
                        (child_id, AssetRelationType.PARENT_OF.value),
                    ).fetchall()
                    for row in rows:
                        old_parent = row["source_asset_id"]
                        db.execute(
                            "DELETE FROM asset_relations WHERE source_asset_id=? AND target_asset_id=? AND relation_type=?",
                            (old_parent, child_id, AssetRelationType.PARENT_OF.value),
                        )
                        db.execute(
                            "DELETE FROM asset_relations WHERE source_asset_id=? AND target_asset_id=? AND relation_type=?",
                            (child_id, old_parent, AssetRelationType.PART_OF.value),
                        )
                        removed += 1

        self.workflow.add_children(parent_asset_id, child_ids)
        return ReparentAssetsResult(
            parent_asset_id=parent_asset_id,
            child_asset_ids=child_ids,
            removed_parent_links=removed,
        )

    def preflight(self, request: PackPreflightRequest) -> PackPreflightResult:
        asset_ids = list(dict.fromkeys(request.asset_ids))
        if request.collection_id:
            asset_ids.extend(self.workflow._collection_asset_ids(request.collection_id))
            asset_ids = list(dict.fromkeys(asset_ids))
        if not asset_ids:
            raise ValueError("Preflight requires at least one asset or Collection")

        issues: list[PackPreflightIssue] = []
        for asset_id in asset_ids:
            try:
                asset = self.library.get(asset_id)
            except LibraryAssetNotFoundError:
                issues.append(
                    PackPreflightIssue(
                        level="error",
                        code="asset_missing",
                        asset_id=asset_id,
                        message="Asset does not exist in the Library",
                    )
                )
                continue

            image_path = self.workspace / asset.image_path
            if not image_path.is_file():
                issues.append(
                    PackPreflightIssue(
                        level="error",
                        code="image_missing",
                        asset_id=asset.id,
                        message=f"Active image is missing: {asset.image_path}",
                    )
                )
                continue

            try:
                with Image.open(image_path) as image:
                    image_size = image.size
            except Exception as exc:
                issues.append(
                    PackPreflightIssue(
                        level="error",
                        code="image_invalid",
                        asset_id=asset.id,
                        message=f"Active image cannot be read: {exc}",
                    )
                )
                continue

            if image_size != (asset.width, asset.height):
                issues.append(
                    PackPreflightIssue(
                        level="warning",
                        code="dimension_metadata_mismatch",
                        asset_id=asset.id,
                        message=f"Metadata is {asset.width}x{asset.height}, file is {image_size[0]}x{image_size[1]}",
                    )
                )

            self._check_layer(asset.id, asset.mask_path, image_size, "mask", request.require_masks, issues)
            self._check_layer(asset.id, asset.alpha_path, image_size, "alpha", request.require_alpha, issues)

            if request.require_reviewed and asset.review_state not in {
                AssetReviewState.APPROVED,
                AssetReviewState.PRODUCTION_READY,
                AssetReviewState.IN_USE,
            }:
                issues.append(
                    PackPreflightIssue(
                        level="error",
                        code="review_required",
                        asset_id=asset.id,
                        message=f"Asset review_state is {asset.review_state.value}; approve it before strict export",
                    )
                )
            elif asset.review_state == AssetReviewState.ARCHIVED:
                issues.append(
                    PackPreflightIssue(
                        level="warning",
                        code="archived_asset",
                        asset_id=asset.id,
                        message="Archived asset is included",
                    )
                )

            if not asset.category or asset.category == "uncategorized":
                issues.append(
                    PackPreflightIssue(
                        level="warning",
                        code="uncategorized",
                        asset_id=asset.id,
                        message="Asset has no production category",
                    )
                )
            if asset.active_version < 1:
                issues.append(
                    PackPreflightIssue(
                        level="error",
                        code="invalid_active_version",
                        asset_id=asset.id,
                        message="Asset active version is invalid",
                    )
                )

        error_count = sum(1 for issue in issues if issue.level == "error")
        warning_count = sum(1 for issue in issues if issue.level == "warning")
        return PackPreflightResult(
            valid=error_count == 0,
            asset_count=len(asset_ids),
            error_count=error_count,
            warning_count=warning_count,
            issues=issues,
        )

    def _check_layer(
        self,
        asset_id: str,
        relative_path: str | None,
        expected_size: tuple[int, int],
        kind: str,
        required: bool,
        issues: list[PackPreflightIssue],
    ) -> None:
        if not relative_path:
            if required:
                issues.append(
                    PackPreflightIssue(
                        level="error",
                        code=f"{kind}_missing",
                        asset_id=asset_id,
                        message=f"Required {kind} path is missing",
                    )
                )
            return
        path = self.workspace / relative_path
        if not path.is_file():
            issues.append(
                PackPreflightIssue(
                    level="error" if required else "warning",
                    code=f"{kind}_missing",
                    asset_id=asset_id,
                    message=f"{kind.title()} file is missing: {relative_path}",
                )
            )
            return
        try:
            with Image.open(path) as image:
                size = image.size
        except Exception as exc:
            issues.append(
                PackPreflightIssue(
                    level="error",
                    code=f"{kind}_invalid",
                    asset_id=asset_id,
                    message=f"{kind.title()} cannot be read: {exc}",
                )
            )
            return
        if size != expected_size:
            issues.append(
                PackPreflightIssue(
                    level="error",
                    code=f"{kind}_size_mismatch",
                    asset_id=asset_id,
                    message=f"{kind.title()} size {size[0]}x{size[1]} does not match image {expected_size[0]}x{expected_size[1]}",
                )
            )

    def _is_descendant(self, ancestor_candidate: str, asset_id: str) -> bool:
        """Return True when asset_id exists below ancestor_candidate."""
        queue = [ancestor_candidate]
        visited: set[str] = set()
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            if current == asset_id:
                return True
            queue.extend(self.workflow._direct_children(current))
        return False
