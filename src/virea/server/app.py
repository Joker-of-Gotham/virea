from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from virea.data.registry import DatasetRegistry
from virea.paths import AVAILABLE_DATA_SOURCES, ProjectPaths, repo_root
from virea.pipelines.catalog import CatalogPipeline
from virea.pipelines.processed_preview import ProcessedPreviewPipeline
from virea.pipelines.raw_preview import RawPreviewPipeline


class ProcessRequest(BaseModel):
    data_source: str | None = None
    dataset: str
    sample_id: str
    max_frames: int | None = None
    persist: bool = True


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

    @app.get("/api/preview")
    def preview(
        data_source: str | None = None,
        dataset: str = Query(...),
        sample_id: str = Query(...),
        stage: Literal["raw", "processed"] = "processed",
        max_frames: int | None = Query(default=None, ge=1, le=1200),
        persist: bool = False,
    ) -> dict:
        try:
            registry = _registry_for(_resolve_data_source(data_source))
            if stage == "raw":
                raw_pipeline = RawPreviewPipeline(registry)
                payload = raw_pipeline.preview(dataset, sample_id, max_frames=max_frames)
            else:
                processed_pipeline = ProcessedPreviewPipeline(registry)
                payload = processed_pipeline.preview(dataset, sample_id, max_frames=max_frames, persist=persist)
            return payload.to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.post("/api/process")
    def process(request: ProcessRequest) -> dict:
        try:
            registry = _registry_for(_resolve_data_source(request.data_source))
            processed_pipeline = ProcessedPreviewPipeline(registry)
            payload = processed_pipeline.preview(
                request.dataset,
                request.sample_id,
                max_frames=request.max_frames,
                persist=request.persist,
            )
            return payload.to_dict()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    return app


app = create_app()
