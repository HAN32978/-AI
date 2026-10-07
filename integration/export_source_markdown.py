"""Produce readable original source, integrated source and diff archives."""

import argparse
import difflib
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile


def redact(text):
    # Preserve variable names while masking any nonempty credential literal.
    return re.sub(
        r'((?:\w*API_KEY|\w*PASSWORD)\s*(?::\s*str)?\s*=\s*)([\"\'])([^\"\'\n]+)\2',
        r'\1"[REDACTED]"', text, flags=re.I,
    )


def archive(title, files, destination):
    sections = [f"# {title}\n\n这是源码阅读归档；执行代码请使用仓库中的实际文件。归档不包含 .env、权重、用户资料或向量库。非空密钥字面量会被遮盖。\n"]
    for name, raw in files.items():
        text = redact(raw.decode("utf-8-sig", errors="replace"))
        language = "python" if name.endswith(".py") else "text"
        sections.append(f"\n## {name}\n\nSHA256：`{hashlib.sha256(raw).hexdigest()}`\n\n```{language}\n{text.rstrip()}\n```\n")
    destination.write_text("\n".join(sections), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project1-zip", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    original = {}
    with ZipFile(args.project1_zip) as zipped:
        settings = next(name for name in zipped.namelist() if name.endswith("/config/settings.py"))
        prefix = settings[:-len("config/settings.py")]
        for name in sorted(zipped.namelist()):
            relative = name.removeprefix(prefix)
            if name.startswith(prefix) and "__pycache__" not in name and (name.endswith(".py") or relative == "requirements.txt"):
                original[relative] = zipped.read(name)
    integrated = {}
    for folder in ("rag_app", "integration"):
        for path in sorted((repo / folder).rglob("*.py")):
            if "__pycache__" not in path.parts:
                integrated[path.relative_to(repo).as_posix()] = path.read_bytes()
    archive("项目一原始源码归档", original, repo / "docs" / "项目一原始源码归档.md")
    archive("修改后整合源码归档", integrated, repo / "docs" / "修改后整合源码归档.md")
    diffs = ["# 项目一到整合版改动对照\n\n逐文件展示原项目一与当前 rag_app 的差异；其中包含以前的监理智查改动，不能全部归因于本次整合。新增工作流代码见修改后源码归档。\n"]
    count = 0
    for relative, raw in original.items():
        path = repo / "rag_app" / relative
        if not path.is_file():
            continue
        before = redact(raw.decode("utf-8-sig", errors="replace")).splitlines()
        after = redact(path.read_text(encoding="utf-8-sig")).splitlines()
        diff = list(difflib.unified_diff(before, after, fromfile=f"project1/{relative}", tofile=f"rag_app/{relative}", lineterm=""))
        if diff:
            count += 1
            diffs.append(f"\n## {relative}\n\n```diff\n" + "\n".join(diff) + "\n```\n")
    (repo / "docs" / "项目一到整合版改动对照.md").write_text("\n".join(diffs), encoding="utf-8")
    print(f"原始文件 {len(original)}；整合文件 {len(integrated)}；有差异文件 {count}")


if __name__ == "__main__":
    main()
