from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from virea.data.registry import DatasetRegistry
from virea.paths import AVAILABLE_DATA_SOURCES, ProjectPaths, repo_root
from virea.pipelines.batch import BatchPipeline, default_worker_count
from virea.pipelines.catalog import CatalogPipeline
from virea.pipelines.preview_reader import PreviewReader
from virea.pipelines.processed_preview import ProcessedPreviewPipeline
from virea.pipelines.processing import ProcessingPipeline
from virea.pipelines.raw_preview import RawPreviewPipeline
from virea.server.binary_codec import pack_positions_binary


class ProcessRequest(BaseModel):
    data_source: str | None = None
    dataset: str
    sample_id: str
    max_frames: int | None = None
    persist: bool = True
    skip_existing: bool = False


class BatchRequest(BaseModel):
    data_source: str | None = None
    datasets: list[str] = Field(default_factory=list)
    query: str = ""
    limit_per_dataset: int = 0
    max_frames: int | None = None
    workers: int = 0
    continue_on_error: bool = True
    skip_existing: bool = True
    force: bool = False


def _default_data_source() -> str:
    return ProjectPaths().data_source


def _resolve_data_source(data_source: str | None) -> str:
    return (data_source or _default_data_source()).strip().lower()


def _mount_static_if_exists(app: FastAPI, route: str, directory: str) -> None:
    path = repo_root().parent / directory
    if path.exists():
        app.mount(route, StaticFiles(directory=str(path)), name=route.strip("/").replace("/", "_"))


@lru_cache(maxsize=4)
def _registry_for(data_source: str) -> DatasetRegistry:
    if data_source not in AVAILABLE_DATA_SOURCES:
        raise KeyError(f"unsupported data source: {data_source}")
    return DatasetRegistry.default(data_source=data_source)


def _preview_query_params(
    data_source: str | None,
    dataset: str,
    sample_id: str,
    max_frames: int | None,
    from_artifacts: bool,
) -> tuple[DatasetRegistry, str, str, str, int | None, bool]:
    resolved = _resolve_data_source(data_source)
    return _registry_for(resolved), resolved, dataset, sample_id, max_frames, from_artifacts


def create_app() -> FastAPI:
    app = FastAPI(title="VIREA Preview Runtime", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ui_root = repo_root() / "apps" / "viewer-web"
    if ui_root.exists():
        app.mount("/ui", StaticFiles(directory=str(ui_root)), name="ui")
    _mount_static_if_exists(
        app,
        "/vendor/three",
        "LLM-driven-VRM/history_try/VRM-executor/node_modules/.pnpm/three@0.183.2/node_modules/three",
    )
    _mount_static_if_exists(
        app,
        "/vendor/three-vrm",
        "LLM-driven-VRM/history_try/VRM-executor/node_modules/.pnpm/@pixiv+three-vrm@3.5.1_three@0.183.2/node_modules/@pixiv/three-vrm",
    )

    @app.get("/")
    def root() -> FileResponse:
        index = ui_root / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="viewer UI is not available")
        return FileResponse(index)

    @app.get("/api/health")
    def health() -> dict:
        current_source = ProjectPaths().data_source
        registry = _registry_for(current_source)
        return {
            "ok": True,
            "default_data_source": registry.paths.data_source,
            "available_data_sources": ProjectPaths.available_sources(),
            "raw_root": str(registry.paths.raw_root),
            "processed_root": str(registry.paths.processed_root),
            "datasets": registry.keys(),
        }

    @app.get("/api/catalog")
    def catalog(data_source: str | None = None) -> dict:
        registry = _registry_for(_resolve_data_source(data_source))
        return CatalogPipeline(registry).summary()

    @app.get("/api/datasets")
    def datasets(data_source: str | None = None) -> dict:
        registry = _registry_for(_resolve_data_source(data_source))
        return registry.to_dict()

    @app.get("/api/samples")
    def samples(
        data_source: str | None = None,
        dataset: str = Query(...),
        q: str = "",
        limit: int = Query(50, ge=1, le=500),
    ) -> dict:
        try:
            resolved_source = _resolve_data_source(data_source)
            registry = _registry_for(resolved_source)
            items = registry.adapter(dataset).discover(limit=limit, query=q)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"data_source": resolved_source, "dataset": dataset, "items": [item.to_dict() for item in items]}

    @app.get("/api/preview/source")
    def preview_source(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        from_artifacts: bool = Query(default=True, alias="from_artifacts"),
    ) -> dict:
        try:
            registry, *_rest = _preview_query_params(data_source, dataset, sample_id, max_frames, from_artifacts)
            reader = PreviewReader(registry)
            if from_artifacts:
                try:
                    return reader.read_source_preview(dataset, sample_id, max_frames=max_frames).to_dict()
                except FileNotFoundError:
                    pass
            return RawPreviewPipeline(registry).preview(dataset, sample_id, max_frames=max_frames).to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.get("/api/preview/processed")
    def preview_processed(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        from_artifacts: bool = Query(default=True, alias="from_artifacts"),
    ) -> dict:
        try:
            registry, *_rest = _preview_query_params(data_source, dataset, sample_id, max_frames, from_artifacts)
            reader = PreviewReader(registry)
            if from_artifacts:
                try:
                    return reader.read_processed_preview(dataset, sample_id, max_frames=max_frames).to_dict()
                except FileNotFoundError:
                    pass
            return ProcessedPreviewPipeline(registry).preview(
                dataset, sample_id, max_frames=max_frames, persist=False
            ).to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.get("/api/preview/motion")
    def preview_motion(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        from_artifacts: bool = Query(default=True, alias="from_artifacts"),
    ) -> dict:
        try:
            registry, *_rest = _preview_query_params(data_source, dataset, sample_id, max_frames, from_artifacts)
            reader = PreviewReader(registry)
            if from_artifacts:
                try:
                    return reader.read_motion_payload(dataset, sample_id, max_frames=max_frames)
                except FileNotFoundError:
                    pass
            payload = ProcessedPreviewPipeline(registry).preview(
                dataset, sample_id, max_frames=max_frames, persist=False
            )
            if payload.motion is None:
                raise HTTPException(status_code=404, detail="motion payload missing")
            return payload.motion
        except HTTPException:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.get("/api/preview/quality")
    def preview_quality_endpoint(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
    ) -> dict:
        try:
            registry = _registry_for(_resolve_data_source(data_source))
            return PreviewReader(registry).read_quality_report(dataset, sample_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _binary_positions(stage: Literal["source", "processed"], **kwargs) -> Response:
        registry, dataset, sample_id, max_frames, from_artifacts = (
            kwargs["registry"],
            kwargs["dataset"],
            kwargs["sample_id"],
            kwargs["max_frames"],
            kwargs["from_artifacts"],
        )
        reader = PreviewReader(registry)
        if stage == "source":
            if from_artifacts:
                try:
                    payload = reader.read_source_preview(dataset, sample_id, max_frames=max_frames)
                except FileNotFoundError:
                    payload = RawPreviewPipeline(registry).preview(dataset, sample_id, max_frames=max_frames)
            else:
                payload = RawPreviewPipeline(registry).preview(dataset, sample_id, max_frames=max_frames)
        else:
            if from_artifacts:
                try:
                    payload = reader.read_processed_preview(dataset, sample_id, max_frames=max_frames)
                except FileNotFoundError:
                    payload = ProcessedPreviewPipeline(registry).preview(
                        dataset, sample_id, max_frames=max_frames, persist=False
                    )
            else:
                payload = ProcessedPreviewPipeline(registry).preview(
                    dataset, sample_id, max_frames=max_frames, persist=False
                )
        positions = payload.positions
        frame_count = int(positions.shape[0])
        joint_count = int(positions.shape[1])
        body = pack_positions_binary(positions, frame_count, joint_count)
        return Response(content=body, media_type="application/octet-stream")

    @app.get("/api/preview/source/binary")
    def preview_source_binary(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        from_artifacts: bool = Query(default=True, alias="from_artifacts"),
    ) -> Response:
        try:
            registry, *_ = _preview_query_params(data_source, dataset, sample_id, max_frames, from_artifacts)
            return _binary_positions(
                "source",
                registry=registry,
                dataset=dataset,
                sample_id=sample_id,
                max_frames=max_frames,
                from_artifacts=from_artifacts,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.get("/api/preview/processed/binary")
    def preview_processed_binary(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        from_artifacts: bool = Query(default=True, alias="from_artifacts"),
    ) -> Response:
        try:
            registry, *_ = _preview_query_params(data_source, dataset, sample_id, max_frames, from_artifacts)
            return _binary_positions(
                "processed",
                registry=registry,
                dataset=dataset,
                sample_id=sample_id,
                max_frames=max_frames,
                from_artifacts=from_artifacts,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.get("/api/preview/on-demand")
    def preview_on_demand(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        stage: Literal["raw", "processed"] = "processed",
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        persist: bool = False,
    ) -> dict:
        """Compute preview in memory without requiring persisted artifacts."""
        try:
            registry = _registry_for(_resolve_data_source(data_source))
            if stage == "raw":
                return RawPreviewPipeline(registry).preview(dataset, sample_id, max_frames=max_frames).to_dict()
            return ProcessedPreviewPipeline(registry).preview(
                dataset, sample_id, max_frames=max_frames, persist=persist
            ).to_dict()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.get("/api/preview")
    def preview_legacy(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        stage: Literal["raw", "processed"] = "processed",
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        persist: bool = False,
        from_artifacts: bool = Query(default=False, alias="from_artifacts"),
    ) -> dict:
        """Deprecated alias: prefer /api/preview/source or /api/preview/processed."""
        if stage == "raw":
            return preview_source(
                data_source=data_source,
                dataset=dataset,
                sample_id=sample_id,
                max_frames=max_frames,
                from_artifacts=from_artifacts or persist,
            )
        if persist:
            return preview_on_demand(
                data_source=data_source,
                dataset=dataset,
                sample_id=sample_id,
                stage="processed",
                max_frames=max_frames,
                persist=True,
            )
        return preview_processed(
            data_source=data_source,
            dataset=dataset,
            sample_id=sample_id,
            max_frames=max_frames,
            from_artifacts=from_artifacts,
        )

    @app.post("/api/process")
    def process(request: ProcessRequest) -> dict:
        try:
            registry = _registry_for(_resolve_data_source(request.data_source))
            output = ProcessingPipeline(registry).run(
                request.dataset,
                request.sample_id,
                max_frames=request.max_frames,
                persist=request.persist,
                skip_existing=request.skip_existing,
            )
            builder_payload = ProcessedPreviewPipeline(registry)._builder.processed_payload(
                output.clip,
                output.canonical,
                source=output.source,
                files=output.paths,
            )
            return builder_payload.to_dict()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.post("/api/batch")
    def batch_process(request: BatchRequest) -> dict:
        try:
            registry = _registry_for(_resolve_data_source(request.data_source))
            pipeline = BatchPipeline(registry)
            limit = request.limit_per_dataset if request.limit_per_dataset > 0 else None
            tasks = pipeline.collect_tasks(
                datasets=request.datasets or None,
                query=request.query,
                limit_per_dataset=limit or 1_000_000_000,
            )
            workers = request.workers if request.workers > 0 else default_worker_count()
            report = pipeline.run(
                tasks,
                workers=workers,
                max_frames=request.max_frames,
                continue_on_error=request.continue_on_error,
                skip_existing=request.skip_existing,
                force=request.force,
            )
            return report.to_dict()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    return app


app = create_app()
