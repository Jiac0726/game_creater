# Asset Intelligence

Asset Intelligence helps a growing 2D library organize itself while preserving human control.

## Principle

Analysis is read-only. Applying suggestions is a separate explicit action.

```text
Analyze
-> suggested category/subcategory/tags
-> quality metrics/issues
-> duplicate candidates
-> human/AI reviews result
-> Apply
```

## Analysis

```text
POST /api/v1/library/intelligence/assets/{asset_id}/analyze
POST /api/v1/library/intelligence/analyze-bulk
```

The current implementation is offline and uses the existing Game Asset Ontology plus active image statistics.

### Classification / tags

Asset name, category, subcategory, tags, notes and ontology entries are matched to propose a game-asset category and useful semantic tags. Existing tags are never silently removed.

### Quality

The report scores:
- minimum resolution
- non-transparent fill ratio
- edge clearance / likely missing padding
- extreme aspect ratio
- transparency presence

It returns both a normalized quality score and concrete issues.

### Duplicate candidates

The active image is compared to other non-archived assets with perceptual dHash. Candidates above the requested similarity threshold are returned for review; the service does not auto-delete or merge them.

## Apply

```text
POST /api/v1/library/intelligence/assets/{asset_id}/apply
```

The request carries the analyzed report and explicit switches controlling whether category, subcategory and tags are applied.

## Human UI

The Asset Intelligence panel supports selected-asset analysis, bulk analysis, report inspection and explicit application of one report.

## AI-native

Analyze and Apply are separate typed actions. An AI agent can inspect large batches without permission to overwrite metadata until the Apply action is intentionally invoked.
