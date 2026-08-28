from __future__ import annotations

from app.services.pipeline import AssetSplitPipeline
from app.services.workflow_manager import WorkflowManager
from app.workflow_models import RunProjectRequest, WorkflowStage


def test_mock_project_workflow_runs_semantics_generation_and_split(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    pipeline = AssetSplitPipeline(tmp_path / "workspace")
    manager = WorkflowManager(tmp_path / "workspace", pipeline)

    project = manager.run(
        RunProjectRequest(
            concept="废弃地铁站",
            provider="mock",
            size="800x450",
            quality="medium",
            auto_split=True,
        )
    )

    assert project.stage == WorkflowStage.ASSET_REVIEW
    assert project.asset_plan is not None
    assert project.asset_plan.assets
    assert project.asset_plan.detection_prompts
    assert project.generation is not None
    assert project.generation.provider == "mock"
    assert project.scene_id

    project_dir = manager.store.project_dir(project.project_id)
    assert (project_dir / "project.json").is_file()
    assert (project_dir / "semantic" / "plan.json").is_file()
    assert (project_dir / "generation" / "request.json").is_file()
    assert (project_dir / "generation" / "metadata.json").is_file()
    assert (project_dir / "generation" / "source.png").is_file()

    scene_dir = tmp_path / "workspace" / project.scene_id
    assert (scene_dir / "scene.json").is_file()
    assert any(event.stage == WorkflowStage.GENERATING for event in project.events)
    assert any(event.stage == WorkflowStage.ASSET_REVIEW for event in project.events)


def test_project_workflow_can_stop_after_generation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GAME_CREATER_MODE", "mock")
    pipeline = AssetSplitPipeline(tmp_path / "workspace")
    manager = WorkflowManager(tmp_path / "workspace", pipeline)

    project = manager.run(
        RunProjectRequest(
            concept="魔法森林",
            provider="mock",
            size="512x512",
            auto_split=False,
        )
    )

    assert project.stage == WorkflowStage.IMAGE_READY
    assert project.scene_id is None
    assert project.generation is not None
