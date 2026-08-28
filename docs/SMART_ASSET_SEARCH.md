# Smart Asset Search

Smart Asset Search adds natural-language and visual similarity retrieval on top of the global Asset Library.

## Default providers

### Ontology + metadata

Always available offline. The query is expanded through the existing Game Asset Ontology and ranked against asset name, category, subcategory, tags, notes and provenance prompts.

### Perceptual dHash

Always available without new ML dependencies. Similarity search compares active asset images using a 64-bit difference hash and mixes optional metadata similarity.

### OpenCLIP slot

`GAME_CREATER_OPENCLIP_URL` is reserved for an optional multimodal adapter. OpenCLIP is intentionally not added to core requirements because its Torch/GPU dependency surface is much heavier than the local Asset Library service.

OpenCLIP itself uses the MIT license. Sentence Transformers is another compatible future text-embedding option under Apache-2.0.

## API

```text
GET  /api/v1/library/smart-search/providers
POST /api/v1/library/smart-search/text
POST /api/v1/library/smart-search/similar
```

Text example:

```json
{
  "query": "废弃地铁站的破旧金属道具",
  "limit": 24
}
```

Similar-image example:

```json
{
  "asset_id": "asset_xxx",
  "limit": 24,
  "include_metadata_similarity": true
}
```

Every result contains the complete Library asset, normalized search score, preview URL and human-readable ranking reasons.

## Human UI

The Smart Asset Search workspace supports natural-language queries and "find similar" from the currently selected Asset Library item. Clicking a result locates the corresponding Library card when it is loaded.

## AI-native

The text and similar-image operations are normal typed `/api/v1/*` actions, so agents can search the same Library without browser automation.
