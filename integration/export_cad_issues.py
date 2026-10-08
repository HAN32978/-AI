"""Export the existing upstream CAD issue pool for the RAG review workflow."""

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "upstream"))


def main() -> int:
    parser = argparse.ArgumentParser(description="运行上游审图并导出问题池 JSON")
    parser.add_argument("--mode", choices=("demo", "dxf"), default="demo")
    parser.add_argument("--dxf-dir", type=Path, help="真实审查所用 DXF 目录")
    parser.add_argument("--project", default="演示项目")
    parser.add_argument("--output-dir", type=Path, default=REPO / "integration" / "output")
    args = parser.parse_args()
    if args.mode == "dxf":
        if not args.dxf_dir or not args.dxf_dir.is_dir() or not list(args.dxf_dir.glob("*.dxf")):
            parser.error("真实审查需要包含 DXF 文件的 --dxf-dir")
        if not (os.getenv("ZHIPU_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
            parser.error("真实审查需要按上游要求配置 ZHIPU_API_KEY 或 DEEPSEEK_API_KEY")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    from v7.master_v7 import run_demo, run_full

    upstream_args = SimpleNamespace(
        output_dir=str(args.output_dir), dxf_dir=str(args.dxf_dir or ""),
        ui=False, port=8080, project=args.project, project_name=args.project,
        conflict_diff=None,
    )
    pool = run_demo(upstream_args) if args.mode == "demo" else run_full(upstream_args)
    output = args.output_dir / "cad_issues.json"
    pool.to_json(str(output))
    print(f"问题池 JSON：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
