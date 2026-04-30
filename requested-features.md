# Requested features for knowledge-base search

## 1. (DONE) Status and indexing are very slow.
Indexing takes a long time to initialize even before the progress bar is shown.
Also check `time sage status` output.

## 2. (DONE) Show the amount of time spent.
This would make it easier to step away for a few minutes while indexing runs and get an idea of how long it took.

## 3. PDF-support
Could this knowledge-base support PDFs?

## 4. (PARTIAL) Use litellm for embeddings
If I want to use this at work (software engineer), AWS Bedrock support is important.
litellm is probably the easiest way to add AWS embeddings.

## 5. Add container and k8s deployments
Also makes this easier to share at work.

## 6. Add optional re-ranker module.

## 7. (DONE) Add `SKILL.md` for the CLI.
May also need a console-only output to hide progress bars.
Could add a query rewrite function.

## 8. Add more logging for observability.

## 9. (DONE) Deduplicate search results.
Hybrid search (dense + BM25) can surface the same chunk twice with nearly identical scores.
Results should be deduplicated by node ID before being returned.

## 10. (DONE) Local qdrant only accepts one connection at a time.
Just move to qdrant server.

## 11. (DONE) Make the config file and pipeline_cache more compatible with XDG_CONFIG

## 12. More document metadata like last modified date

## 13. (DONE) Tags for knowledge bases that can be used for filtering
Having groups of knowledge bases would make this much more useful.

## 14. (DONE) Fix location of `pipeline_cache`

## 15. (DONE) Fix stale qdrant rows.

## 16. (DONE) Add E2E tests

## 17. Add unit tests
