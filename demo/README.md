# VIREA Local Demo Data

`demo/raw/` and `demo/processed/` are local, ignored directories.

Build a same-layout miniature fixture from the full local raw data source:

```powershell
$env:PYTHONPATH = "D:\AI-Program-Project\virea\src"
python -m virea.cli build-demo --overwrite
```

Then run the same pipeline against the demo source:

```powershell
python -m virea.cli samples --data-source demo --dataset beat --limit 1
python -m virea.cli process --data-source demo --dataset beat --limit 1
python -m virea.cli verify --data-source demo --max-frames 16 --out demo/verification-report.json
python scripts/smoke_pipeline.py --data-source demo --max-frames 8
python -m virea.cli serve --data-source demo --port 8013
```

The demo layout mirrors the full raw layout:

```text
demo/raw/
  amass/
  babel/
  beat/
  grab/
  humanml3d/
  motionx/
  SuSuInterActs/
```

Do not commit copied third-party raw data.

`demo/raw/`, `demo/processed/`, `demo/manifest.json`, and
`demo/verification-report.json` are local generated artifacts and are ignored by
Git.
