from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.asset_library_models import (
    AssetRelationRequest,
    AssetSearchResult,
    BulkLibraryAssetPatch,
    CollectionMembershipRequest,
    CreateCollectionRequest,
    LibraryAsset,
    LibraryAssetPatch,
    LibraryAssetVersion,
)
from app.services.asset_library import (
    AssetLibrary,
    CollectionNotFoundError,
    LibraryAssetNotFoundError,
)
from app.services.asset_library_sync import apply_library_metadata_to_scene


def build_asset_library_router(workspace: str | Path) -> APIRouter:
    router = APIRouter(prefix="/library", tags=["asset-library"])
    library = AssetLibrary(workspace)

    @router.get("/stats")
    def stats():
        return library.stats()

    @router.get("/assets", response_model=AssetSearchResult)
    def search_assets(
        q: str = "",
        category: str | None = None,
        review_state: str | None = None,
        collection_id: str | None = None,
        favorite: bool | None = None,
        completed: bool | None = None,
        min_score: float | None = Query(default=None, ge=0, le=1),
        tags: str = "",
        limit: int = Query(default=60, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> AssetSearchResult:
        tag_list = [value.strip() for value in tags.split(",") if value.strip()]
        return library.search(
            query=q,
            category=category,
            review_state=review_state,
            collection_id=collection_id,
            favorite=favorite,
            completed=completed,
            min_score=min_score,
            tags=tag_list,
            limit=limit,
            offset=offset,
        )

    @router.get("/assets/{asset_id}", response_model=LibraryAsset)
    def get_asset(asset_id: str) -> LibraryAsset:
        try:
            return library.get(asset_id)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.patch("/assets/{asset_id}", response_model=LibraryAsset)
    def patch_asset(asset_id: str, patch: LibraryAssetPatch) -> LibraryAsset:
        try:
            updated = library.patch(asset_id, patch)
            apply_library_metadata_to_scene(workspace, updated)
            return updated
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/assets/bulk")
    def bulk_patch_assets(request: BulkLibraryAssetPatch) -> dict:
        updated_ids: list[str] = []
        try:
            for asset_id in request.asset_ids:
                current = library.get(asset_id)
                tags = list(current.tags)
                if request.add_tags:
                    existing = {value.lower() for value in tags}
                    for tag in request.add_tags:
                        clean = tag.strip()
                        if clean and clean.lower() not in existing:
                            existing.add(clean.lower())
                            tags.append(clean)
                if request.remove_tags:
                    remove = {value.strip().lower() for value in request.remove_tags if value.strip()}
                    tags = [value for value in tags if value.lower() not in remove]

                patch_data: dict = {"tags": tags}
                if request.review_state is not None:
                    patch_data["review_state"] = request.review_state
                if request.favorite is not None:
                    patch_data["favorite"] = request.favorite
                updated = library.patch(asset_id, LibraryAssetPatch(**patch_data))
                apply_library_metadata_to_scene(workspace, updated)
                updated_ids.append(asset_id)
            return {"ok": True, "updated": updated_ids, "count": len(updated_ids)}
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/assets/{asset_id}/versions", response_model=list[LibraryAssetVersion])
    def versions(asset_id: str) -> list[LibraryAssetVersion]:
        try:
            library.get(asset_id)
            return library.list_versions(asset_id)
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.get("/assets/{asset_id}/relations")
    def relations(asset_id: str) -> dict:
        try:
            library.get(asset_id)
            return {"relations": library.relations(asset_id)}
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.post("/assets/{asset_id}/relations")
    def add_relation(asset_id: str, request: AssetRelationRequest) -> dict:
        try:
            library.add_relation(asset_id, request.target_asset_id, request.relation_type)
            return {"ok": True, "relations": library.relations(asset_id)}
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/collections")
    def collections() -> dict:
        return {"collections": library.list_collections()}

    @router.post("/collections")
    def create_collection(request: CreateCollectionRequest) -> dict:
        try:
            return library.create_collection(request.name, request.description)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/collections/{collection_id}/assets")
    def add_collection_assets(
        collection_id: str,
        request: CollectionMembershipRequest,
    ) -> dict:
        try:
            library.add_to_collection(collection_id, request.asset_ids)
            return {"ok": True, "collection_id": collection_id, "asset_ids": request.asset_ids}
        except CollectionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Collection not found") from exc
        except LibraryAssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library asset not found") from exc

    @router.delete("/collections/{collection_id}/assets/{asset_id}")
    def remove_collection_asset(collection_id: str, asset_id: str) -> dict:
        library.remove_from_collection(collection_id, asset_id)
        return {"ok": True}

    return router
