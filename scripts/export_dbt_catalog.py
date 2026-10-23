"""Build catalog/dbt_models.json from a dbt project.

Usage:
    python scripts/export_dbt_catalog.py --manifest path/to/target/manifest.json
    python scripts/export_dbt_catalog.py --project-dir path/to/dbt_project
    python scripts/export_dbt_catalog.py --github owner/repo [--ref main] [--subdir dbt]   # token: env DBT_GITHUB_TOKEN or GITHUB_TOKEN

See agent/catalog_sync.py for how models and their metadata are read.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import catalog_sync, config  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest")
    group.add_argument("--project-dir")
    group.add_argument("--github", help="owner/repo")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--subdir", default="", help="dbt project folder inside the repo")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.manifest:
        models, origin = catalog_sync.from_manifest_file(args.manifest), f"manifest:{args.manifest}"
    elif args.project_dir:
        models, origin = catalog_sync.from_local_project(args.project_dir), f"local:{args.project_dir}"
    else:
        models = catalog_sync.from_github(args.github, config.dbt_github_token(), args.ref, args.subdir)
        origin = f"github:{args.github}@{args.ref}/{args.subdir}"

    out = catalog_sync.save_catalog(models, origin, args.out)
    print(f"Exported {len(models)} models -> {out}")
