# VIREA Demo Fixture

`demo/` is the local quick-test workspace for the full pipeline.

```text
demo/raw/        # same-layout tiny raw fixture copied from the local full source
demo/processed/  # generated source/canonical/VRM artifacts
```

Build or refresh it with:

```powershell
python -m virea.cli build-demo --samples-per-dataset 7 --overwrite
python -m virea.cli process --data-source demo --workers 8 --force
python -m virea.cli serve --data-source demo
```

Important: `demo/raw` and `demo/processed` can still contain third-party
dataset-derived files. They are intentionally ignored by Git. The lightweight,
committed demo evidence is the rendered 7 x 7 VRM showcase under
`doc/showcase/videos/`.
