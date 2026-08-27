# Real GPU / WSL2 Validation

This protocol validates the first real local path:

```text
Chinese scene concept or English prompts
→ GroundingDINO
→ box dedupe
→ SAM2/SAM2.1
→ mask dedupe
→ RGBA assets / masks / overlay / scene.json
→ optional point-prompt correction
```

The goal is not merely to prove that the server starts. A validation run should prove that CUDA compilation, model loading, inference, asset export and output integrity all work together.

## 1. Recommended environment

- Windows 11 + WSL2 Ubuntu, or native Linux
- NVIDIA GPU visible from WSL (`nvidia-smi` works)
- Python 3.10+
- PyTorch >= 2.3.1 and TorchVision >= 0.18.1 with CUDA support
- CUDA toolkit installed inside WSL/Linux
- `CUDA_HOME` points to a toolkit containing `bin/nvcc`

The official Grounded-SAM-2 project currently documents Python 3.10, torch >= 2.3.1, torchvision >= 0.18.1 and a CUDA compilation environment because GroundingDINO builds a Deformable Attention operator.

## 2. Install and verify

From the Game Creater repository root:

```bash
bash scripts/setup_grounded_sam2_wsl.sh
```

The setup script creates:

```text
~/.config/game_creater/grounded_sam2.env
```

It records the concrete Grounded-SAM-2 commit and model paths.

Verify again at any time:

```bash
python scripts/verify_grounded_sam2_env.py
```

All required checks should be `PASS` before real inference.

## 3. Start the web app

```bash
bash scripts/start_grounded_sam2_wsl.sh
```

Open:

```text
http://127.0.0.1:8000
```

Status endpoint:

```text
http://127.0.0.1:8000/api/v1/models/status
```

## 4. Run one command-line real-image smoke test

Using the local semantic ontology:

```bash
python scripts/smoke_test_grounded_sam2.py \
  --image /mnt/c/path/to/scene.png \
  --keyword "废弃地铁站"
```

Or explicit English prompts:

```bash
python scripts/smoke_test_grounded_sam2.py \
  --image /mnt/c/path/to/scene.png \
  --prompts "subway platform,ticket gate,ticket machine,bench,cable"
```

The command prints JSON containing:

- final `scene_id`
- output directory
- detected asset count
- per-asset confidence and Asset Score
- `raw_detections`
- `after_box_dedupe`
- `after_mask_dedupe`
- duplicate-removal counts

## 5. Validate exported files

Take the `scene_dir` returned by the smoke test:

```bash
python scripts/validate_scene_output.py validation_output/<scene_id>
```

The validator checks:

- every bbox is inside the source scene
- transparent PNG exists
- Mask exists
- cropped PNG/Mask dimensions match the bbox
- PNG alpha is non-empty
- Mask is non-empty
- PNG alpha and stored Mask are consistent
- high-IoU duplicate Mask candidates are reported

Integrity errors return a non-zero exit code. Duplicate candidates are reported for review but do not automatically fail the run.

## 6. Minimum acceptance criteria

For each real test image:

```text
Environment verifier: PASS
Pipeline exits: 0
scene.json exists: yes
Overlay exists: yes
Asset PNG/Mask files missing: 0
Empty Masks: 0
Out-of-bounds bboxes: 0
raw_detections >= after_box_dedupe >= after_mask_dedupe
asset_count == after_mask_dedupe   (real Grounded-SAM2 mode)
```

Human quality review should additionally record:

```text
Useful asset precision = useful exported assets / all exported assets
Missed important assets = important visible assets not exported
Duplicate exports = visually same object exported more than once
Manual corrections = number of delete/merge/split/SAM-click operations needed
```

For the first milestone, a practical target is not perfection. The goal is to make most major scene assets usable with a small number of manual corrections.

## 7. Suggested validation set

Use at least 2–3 images for each scene type rather than tuning on a single image:

| Scene | Key objects to inspect |
|---|---|
| Forest | trees, rocks, bushes, mushrooms, bridge/cabin |
| Abandoned subway | platform, gates, machines, benches, signs, cables |
| Factory | pipes, tanks, machines, barrels, stairs |
| Fishing village | houses, pier, boats, nets, barrels, crates |
| Cave | rocks, crystals, bridge/supports, mushrooms |
| Castle | walls, tower, gate, barrels, statues |
| Tavern | tables, chairs, barrels, bottles, fireplace |
| City alley | doors, windows, signs, bins, bicycles, lamps |

Keep the validation images outside Git or in a locally ignored directory if their licenses are unclear.

## 8. Common failures

### PyTorch sees CUDA but GroundingDINO installation fails

Check:

```bash
echo "$CUDA_HOME"
"$CUDA_HOME/bin/nvcc" --version
```

PyTorch CUDA runtime availability is not the same as having the CUDA compiler toolkit required by GroundingDINO.

### WSL cannot see the GPU

Run:

```bash
nvidia-smi
```

Fix the Windows NVIDIA/WSL GPU setup before debugging Game Creater.

### Too many duplicate assets

Inspect `scene.json -> inference_stats` and tune:

```text
GAME_CREATER_DEDUPE_IOU
GAME_CREATER_CROSS_LABEL_DEDUPE_IOU
GAME_CREATER_MASK_DEDUPE_IOU
GAME_CREATER_CROSS_LABEL_MASK_DEDUPE_IOU
```

Use the default values first. Lower thresholds remove duplicates more aggressively; overly low thresholds can remove legitimate neighboring/nested assets.

### Important object is missed

First add a more specific English detection prompt. If the object is visible but still not found, use the SAM point-prompt correction mode to create it manually from positive/negative clicks.
