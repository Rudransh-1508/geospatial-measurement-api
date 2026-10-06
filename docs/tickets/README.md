# Tickets

Vertical slices in implementation order. Each ticket lists its dependencies and the ADRs it implements.

| # | Ticket | Depends on | Status |
|---|--------|-----------|--------|
| [T01](T01-project-skeleton.md) | Project skeleton, tooling, docker compose | - | Done |
| [T02](T02-database-models.md) | Database models and migrations | T01 | Done |
| [T03](T03-upload-endpoint.md) | Upload endpoint with validation and zip safety | T02 | Done |
| [T04](T04-readers.md) | Shapefile and KML/KMZ readers with CRS normalization | T01 | Done |
| [T05](T05-measurement-engine.md) | Measurement engine | T01 | Done |
| [T06](T06-processing-pipeline.md) | Processing pipeline, Celery task, inline mode | T03, T04, T05 | Done |
| [T07](T07-measurements-endpoint.md) | File info and measurements endpoints | T06 | Done |
| [T08](T08-integration-and-ci.md) | Integration tests, E2E, CI | T07 | Done |
| [T09](T09-readme.md) | README | T08 | Done |
| [T10](T10-accuracy-benchmark.md) | Accuracy benchmark | T05 | Done |
| [T11](T11-map-viewer.md) | Leaflet map viewer | T07 | Done |
| [T12](T12-publish.md) | Publish public GitHub repo | T09 | Done |
