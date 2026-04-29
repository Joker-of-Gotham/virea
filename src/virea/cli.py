from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

import uvicorn

from virea.data.registry import DatasetRegistry
from virea.demo import build_demo_dataset
from virea.paths import AVAILABLE_DATA_SOURCES, ProjectPaths
from virea.pipelines.catalog import CatalogPipeline
from virea.pipelines.processed_preview import ProcessedPreviewPipeline
from virea.pipelines.raw_preview import RawPreviewPipeline
from virea.motion.skeleton import control_rest_alignment_audit
from virea.verification import verify_all, write_verification_report


def _registry(data_source: str) -> DatasetRegistry:
    return DatasetRegistry.default(data_source=data_source)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_catalog(args: argparse.Namespace) -> None:
    registry = _registry(args.data_source)
    summary = CatalogPipeline(registry).summary()
    _print_json(summary)


def _cmd_sources(args: argparse.Namespace) -> None:
    _print_json(ProjectPaths.available_sources())


def _cmd_samples(args: argparse.Namespace) -> None:
    registry = _registry(args.data_source)
    samples = registry.adapter(args.dataset).discover(limit=args.limit, query=args.query)
    _print_json([sample.to_dict() for sample in samples])


def _cmd_process(args: argparse.Namespace) -> None:
    registry = _registry(args.data_source)
    pipeline = ProcessedPreviewPipeline(registry)
    samples = registry.adapter(args.dataset).discover(limit=args.limit, query=args.query)
    outputs = []
    for sample in samples:
        payload = pipeline.preview(args.dataset, sample.sample_id, max_frames=args.max_frames, persist=True)
        outputs.append({"sample_id": sample.sample_id, "files": payload.files, "quality": payload.quality})
    _print_json(outputs)


def _configure_roots_for_conversion(args: argparse.Namespace) -> tuple[Path, Path]:
    defaults = ProjectPaths(data_source=args.data_source)
    if args.data_source == "demo":
        raw_root = Path(args.input_root).expanduser() if args.input_root else defaults.raw_root
        output_root = Path(args.output_root).expanduser() if args.output_root else defaults.processed_root
    else:
        raw_text = args.input_root or input(f"Full raw input root [{defaults.raw_root}]: ").strip() or str(defaults.raw_root)
        out_text = args.output_root or input(f"Full processed output root [{defaults.processed_root}]: ").strip() or str(defaults.processed_root)
        raw_root = Path(raw_text).expanduser()
        output_root = Path(out_text).expanduser()
    if not raw_root.exists():
        raise SystemExit(f"input root does not exist: {raw_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    os.environ["VIREA_RAW_ROOT"] = str(raw_root)
    os.environ["VIREA_PROCESSED_ROOT"] = str(output_root)
    return raw_root, output_root


def _cmd_convert(args: argparse.Namespace) -> None:
    raw_root, output_root = _configure_roots_for_conversion(args)
    registry = _registry(args.data_source)
    pipeline = ProcessedPreviewPipeline(registry)
    datasets = args.datasets or registry.keys()
    limit = args.limit_per_dataset if args.limit_per_dataset and args.limit_per_dataset > 0 else 1_000_000_000
    report = {
        "schema_version": "virea.conversion_report.v0.1.0",
        "data_source": args.data_source,
        "raw_root": str(raw_root),
        "processed_root": str(output_root),
        "max_frames": args.max_frames,
        "datasets": [],
    }
    print(f"[virea] conversion start source={args.data_source} raw={raw_root} out={output_root}", flush=True)
    start = perf_counter()
    total_ok = 0
    total_failed = 0
    for dataset in datasets:
        adapter = registry.adapter(dataset)
        samples = adapter.discover(limit=limit, query=args.query)
        dataset_report = {"dataset": dataset, "total": len(samples), "processed": 0, "failed": 0, "items": []}
        report["datasets"].append(dataset_report)
        print(f"[virea] dataset {dataset}: {len(samples)} samples", flush=True)
        for index, sample in enumerate(samples, start=1):
            item_start = perf_counter()
            try:
                payload = pipeline.preview(dataset, sample.sample_id, max_frames=args.max_frames, persist=True)
                elapsed = perf_counter() - item_start
                dataset_report["processed"] += 1
                total_ok += 1
                dataset_report["items"].append(
                    {
                        "sample_id": sample.sample_id,
                        "status": "passed",
                        "frame_count": int(payload.positions.shape[0]),
                        "fps": payload.fps,
                        "quality": payload.quality,
                        "files": payload.files,
                    }
                )
                print(
                    f"[virea] {dataset} {index}/{len(samples)} ok frames={int(payload.positions.shape[0])} "
                    f"joints={len(payload.joint_names)} elapsed={elapsed:.2f}s",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                elapsed = perf_counter() - item_start
                dataset_report["failed"] += 1
                total_failed += 1
                dataset_report["items"].append({"sample_id": sample.sample_id, "status": "failed", "error": str(exc)})
                print(f"[virea] {dataset} {index}/{len(samples)} failed elapsed={elapsed:.2f}s error={exc}", flush=True)
                if not args.continue_on_error:
                    if args.report:
                        report_path = Path(args.report)
                        report_path.parent.mkdir(parents=True, exist_ok=True)
                        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise
    report["processed"] = total_ok
    report["failed"] = total_failed
    report["elapsed_sec"] = round(perf_counter() - start, 3)
    report["passed"] = total_failed == 0
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[virea] report written: {report_path}", flush=True)
    _print_json(report if args.json else {"processed": total_ok, "failed": total_failed, "elapsed_sec": report["elapsed_sec"]})
    if total_failed:
        raise SystemExit(1)


def _cmd_serve(args: argparse.Namespace) -> None:
    os.environ["VIREA_DATA_SOURCE"] = args.data_source
    uvicorn.run("virea.server.app:app", host=args.host, port=args.port, reload=args.reload)


def _cmd_build_demo(args: argparse.Namespace) -> None:
    manifest = build_demo_dataset(max_rows=args.max_rows, overwrite=args.overwrite)
    _print_json(manifest)


def _cmd_verify(args: argparse.Namespace) -> None:
    report = verify_all(args.data_source, max_frames=args.max_frames, persist=not args.no_persist)
    if args.out:
        write_verification_report(report, args.out)
    _print_json(report)
    if not report.get("passed", False):
        raise SystemExit(1)


def _cmd_vrm_audit(args: argparse.Namespace) -> None:
    report = control_rest_alignment_audit()
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_json(report)
    if not report.get("passed", False):
        raise SystemExit(1)


def _choose(prompt: str, options: list[str], default_index: int = 0) -> str:
    print(prompt)
    for index, item in enumerate(options, start=1):
        marker = " [default]" if index - 1 == default_index else ""
        print(f"  {index}. {item}{marker}")
    raw = input("> ").strip()
    if not raw:
        return options[default_index]
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    if raw in options:
        return raw
    raise SystemExit(f"invalid selection: {raw}")


def _cmd_interactive(args: argparse.Namespace) -> None:
    sources = ProjectPaths.available_sources()
    source_options = list(AVAILABLE_DATA_SOURCES)
    source = _choose(
        "Select data source:",
        [f"{key} - {sources[key].get('label', key)} ({sources[key].get('raw_root', '')})" for key in source_options],
    ).split(" - ", 1)[0]
    registry = _registry(source)

    action = _choose("Select action:", ["catalog", "samples", "preview-both", "process", "convert", "verify", "vrm-audit", "serve"])
    if action == "catalog":
        _print_json(CatalogPipeline(registry).summary())
        return
    if action == "verify":
        max_frames_raw = input("Max frames [120]: ").strip()
        max_frames = int(max_frames_raw) if max_frames_raw else 120
        _print_json(verify_all(source, max_frames=max_frames, persist=True))
        return
    if action == "vrm-audit":
        _print_json(control_rest_alignment_audit())
        return
    if action == "serve":
        os.environ["VIREA_DATA_SOURCE"] = source
        uvicorn.run("virea.server.app:app", host=args.host, port=args.port, reload=False)
        return
    if action == "convert":
        defaults = ProjectPaths(data_source=source)
        if source == "demo":
            raw_root = input(f"Demo raw input root [{defaults.raw_root}]: ").strip() or str(defaults.raw_root)
            output_root = input(f"Demo processed output root [{defaults.processed_root}]: ").strip() or str(defaults.processed_root)
        else:
            raw_root = input(f"Full raw input root [{defaults.raw_root}]: ").strip() or str(defaults.raw_root)
            output_root = input(f"Full processed output root [{defaults.processed_root}]: ").strip() or str(defaults.processed_root)
        dataset_raw = input("Datasets to convert, space separated [all]: ").strip()
        query = input("Search query (optional): ").strip()
        limit_raw = input("Limit per dataset [all]: ").strip()
        max_frames_raw = input("Max frames [all, do not set for final conversion]: ").strip()
        report_default = str(Path(output_root) / "conversion-report.json")
        report = input(f"Report path [{report_default}]: ").strip() or report_default
        convert_args = argparse.Namespace(
            data_source=source,
            input_root=raw_root,
            output_root=output_root,
            datasets=dataset_raw.split() if dataset_raw else [],
            query=query,
            limit_per_dataset=int(limit_raw) if limit_raw else 0,
            max_frames=int(max_frames_raw) if max_frames_raw else None,
            continue_on_error=True,
            report=report,
            json=False,
        )
        _cmd_convert(convert_args)
        return

    dataset = _choose("Select dataset:", registry.keys())
    query = input("Search query (optional): ").strip()
    samples = registry.adapter(dataset).discover(limit=20, query=query)
    if not samples:
        raise SystemExit(f"no samples found for {source}/{dataset}")
    if action == "samples":
        _print_json([item.to_dict() for item in samples])
        return

    sample = _choose("Select sample:", [item.sample_id for item in samples])
    max_frames_raw = input("Max frames [all]: ").strip()
    max_frames = int(max_frames_raw) if max_frames_raw else None

    if action == "preview-both":
        raw_payload = RawPreviewPipeline(registry).preview(dataset, sample, max_frames=max_frames)
        processed_payload = ProcessedPreviewPipeline(registry).preview(dataset, sample, max_frames=max_frames)
        _print_json({"raw": raw_payload.to_dict(), "processed": processed_payload.to_dict()})
        return
    if action == "process":
        payload = ProcessedPreviewPipeline(registry).preview(dataset, sample, max_frames=max_frames, persist=True)
        _print_json({"sample_id": sample, "files": payload.files, "quality": payload.quality})
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="virea")
    source_parent = argparse.ArgumentParser(add_help=False)
    source_parent.add_argument("--data-source", choices=AVAILABLE_DATA_SOURCES, default=os.getenv("VIREA_DATA_SOURCE", "full"))
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="List configured data sources.")
    sources.set_defaults(func=_cmd_sources)

    catalog = sub.add_parser("catalog", parents=[source_parent], help="Summarize raw dataset roots.")
    catalog.set_defaults(func=_cmd_catalog)

    samples = sub.add_parser("samples", parents=[source_parent], help="List samples from one dataset.")
    samples.add_argument("--dataset", required=True)
    samples.add_argument("--query", default="")
    samples.add_argument("--limit", type=int, default=20)
    samples.set_defaults(func=_cmd_samples)

    process = sub.add_parser("process", parents=[source_parent], help="Persist processed canonical/VRM preview payloads.")
    process.add_argument("--dataset", required=True)
    process.add_argument("--query", default="")
    process.add_argument("--limit", type=int, default=1)
    process.add_argument("--max-frames", type=int, default=None)
    process.set_defaults(func=_cmd_process)

    convert = sub.add_parser("convert", parents=[source_parent], help="Convert raw datasets into persisted canonical/VRM artifacts with progress.")
    convert.add_argument("--input-root", default="", help="Raw dataset root. Demo defaults to demo/raw; full prompts when omitted.")
    convert.add_argument("--output-root", default="", help="Processed output root. Demo defaults to demo/processed; full prompts when omitted.")
    convert.add_argument("--datasets", nargs="*", default=[], help="Optional dataset keys to convert. Defaults to all registered datasets.")
    convert.add_argument("--query", default="", help="Optional sample query filter.")
    convert.add_argument("--limit-per-dataset", type=int, default=0, help="0 means no explicit limit.")
    convert.add_argument("--max-frames", type=int, default=None, help="Optional preview/debug frame cap. Omit for full clips.")
    convert.add_argument("--continue-on-error", action="store_true")
    convert.add_argument("--report", default="", help="Optional JSON report path.")
    convert.add_argument("--json", action="store_true", help="Print full JSON report to stdout.")
    convert.set_defaults(func=_cmd_convert)

    verify = sub.add_parser("verify", parents=[source_parent], help="Run mathematical end-to-end verification.")
    verify.add_argument("--max-frames", type=int, default=120)
    verify.add_argument("--no-persist", action="store_true")
    verify.add_argument("--out", default="")
    verify.set_defaults(func=_cmd_verify)

    vrm_audit = sub.add_parser("vrm-audit", help="Audit the true VRM control-rest template derived from imported avatar files.")
    vrm_audit.add_argument("--out", default="", help="Optional JSON audit report path.")
    vrm_audit.set_defaults(func=_cmd_vrm_audit)

    build_demo = sub.add_parser("build-demo", help="Create demo/raw with the same layout as the full raw source.")
    build_demo.add_argument("--max-rows", type=int, default=4, help="Rows copied for compact parquet shards.")
    build_demo.add_argument("--overwrite", action="store_true", help="Replace existing demo/raw before copying.")
    build_demo.set_defaults(func=_cmd_build_demo)

    serve = sub.add_parser("serve", parents=[source_parent], help="Run the unified preview frontend.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8013)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    interactive = sub.add_parser("interactive", parents=[source_parent], help="Choose data source, dataset, and pipeline interactively.")
    interactive.add_argument("--host", default="127.0.0.1")
    interactive.add_argument("--port", type=int, default=8013)
    interactive.set_defaults(func=_cmd_interactive)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
