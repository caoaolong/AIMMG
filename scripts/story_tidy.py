import argparse
import json
import re
from pathlib import Path

from paddleocr import PaddleOCRVL

from utils import scan_files

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# PaddleOCRVL 分页输出命名：stem_N.md / stem_N_res.json
RE_MD = re.compile(r"^(.+)_(\d+)\.md$")
RE_JSON = re.compile(r"^(.+)_(\d+)_res\.json$")


def collect_page_files(output_dir: Path) -> dict[tuple[str, str], dict]:
    """
    扫描 output_dir 下所有 stem_N.md 与 stem_N_res.json，
    按 (parent_relpath, stem) 分组，返回 {(parent, stem): {"md": [(idx, path)], "json": [(idx, path)]}}。
    """
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        return {}

    groups: dict[tuple[str, str], dict] = {}

    for f in output_dir.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(output_dir)
        except ValueError:
            continue
        parent_rel = str(rel.parent) if rel.parent.parts else ""
        name = f.name

        m = RE_MD.match(name)
        if m:
            stem, idx = m.group(1), int(m.group(2))
            key = (parent_rel, stem)
            if key not in groups:
                groups[key] = {"md": [], "json": []}
            groups[key]["md"].append((idx, f))
            continue
        m = RE_JSON.match(name)
        if m:
            stem, idx = m.group(1), int(m.group(2))
            key = (parent_rel, stem)
            if key not in groups:
                groups[key] = {"md": [], "json": []}
            groups[key]["json"].append((idx, f))

    return groups


def run_merge(story_id: str, add_page_break: bool = True) -> None:
    """将 output 下同 stem 的分页 .md / _res.json 合并为单个文件。"""
    out_dir = PROJECT_ROOT / "stories" / story_id / "output"
    if not out_dir.is_dir():
        print(f"目录不存在: {out_dir}")
        return

    groups = collect_page_files(out_dir)
    if not groups:
        print("未找到可分页合并的 OCR 输出文件（stem_N.md / stem_N_res.json）")
        return

    for (parent_rel, stem), files in sorted(groups.items()):
        parent_dir = out_dir / parent_rel if parent_rel else out_dir
        md_list = sorted(files["md"], key=lambda x: x[0])
        json_list = sorted(files["json"], key=lambda x: x[0])

        if md_list:
            parts = []
            for idx, path in md_list:
                text = path.read_text(encoding="utf-8").strip()
                if add_page_break and parts:
                    parts.append("\n\n---\n\n## 第 {} 页\n\n".format(idx + 1))
                parts.append(text)
            merged_md = "\n\n".join(parts)
            out_md = parent_dir / f"{stem}_merged.md"
            out_md.write_text(merged_md, encoding="utf-8")
            print(f"  MD: {parent_rel or '.'}/{stem}_merged.md ({len(md_list)} 页)")

        if json_list:
            pages = []
            for _idx, path in json_list:
                with open(path, "r", encoding="utf-8") as fp:
                    pages.append(json.load(fp))
            merged_json = {"pages": pages, "source_stem": stem}
            out_json = parent_dir / f"{stem}_merged.json"
            with open(out_json, "w", encoding="utf-8") as fp:
                json.dump(merged_json, fp, ensure_ascii=False, indent=2)
            print(f"  JSON: {parent_rel or '.'}/{stem}_merged.json ({len(json_list)} 页)")

        # 合并成功后删除原分页文件
        for _idx, path in md_list:
            try:
                path.unlink()
            except OSError as e:
                print(f"  删除失败 {path}: {e}")
        for _idx, path in json_list:
            try:
                path.unlink()
            except OSError as e:
                print(f"  删除失败 {path}: {e}")


def run_clean(story_id: str) -> None:
    """清除指定 story_id 下 output 目录中的所有 .json 文件。"""
    out_dir = PROJECT_ROOT / "stories" / story_id / "output"
    if not out_dir.is_dir():
        print(f"目录不存在: {out_dir}")
        return

    deleted = 0
    for path in out_dir.rglob("*.json"):
        if not path.is_file():
            continue
        try:
            path.unlink()
            deleted += 1
            print(f"  已删除: {path.relative_to(out_dir)}")
        except OSError as e:
            print(f"  删除失败 {path}: {e}")
    print(f"共删除 {deleted} 个 JSON 文件")


def main():
    parser = argparse.ArgumentParser(description="剧本 OCR 整理：识别 PDF 或合并已识别结果")
    parser.add_argument("--id", default="shou_huo_ri", help="剧本 ID，对应 stories/<id>")
    sub = parser.add_subparsers(dest="command", required=False, help="子命令")

    # 默认：对 stories/<id> 下 PDF 做 PaddleOCRVL 识别
    parser_ocr = sub.add_parser("ocr", help="对剧本目录下 PDF 进行 OCR（默认子命令）")
    parser_ocr.add_argument("--id", default="shou_huo_ri", help="剧本 ID")

    # merge：合并 output 下同 stem 的分页 md/json
    parser_merge = sub.add_parser("merge", help="合并 output 下 PaddleOCRVL 分页结果为单个文件")
    parser_merge.add_argument("--id", default="shou_huo_ri", help="剧本 ID")
    parser_merge.add_argument(
        "--no-page-break",
        action="store_true",
        help="合并 MD 时不插入「第 N 页」分隔",
    )

    # clean：清除 output 下所有 json 文件
    parser_clean = sub.add_parser("clean", help="清除指定剧本 output 目录下所有 JSON 文件")
    parser_clean.add_argument("--id", default="shou_huo_ri", help="剧本 ID")

    args = parser.parse_args()
    story_id = getattr(args, "id", "shou_huo_ri")
    command = args.command if args.command else "ocr"

    if command == "merge":
        run_merge(story_id, add_page_break=not getattr(args, "no_page_break", False))
        return
    if command == "clean":
        run_clean(story_id)
        return

    # 默认 OCR 流程
    story_path = PROJECT_ROOT / "stories" / story_id
    if not story_path.is_dir():
        print(f"目录不存在: {story_path}")
        exit(1)

    pdf_list = scan_files(story_path, ".pdf", recursive=True)
    if not pdf_list:
        print("未找到 PDF 文件")
        exit(0)

    pipeline = PaddleOCRVL()
    out_dir = story_path / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, item in enumerate(pdf_list, 1):
        name, relpath = item["name"], item["relpath"]
        full_path = story_path / relpath
        print(f"[{i}/{len(pdf_list)}] {relpath}")
        try:
            output = pipeline.predict(input=str(full_path))
            for res in output:
                stem = Path(relpath).stem
                sub_out = out_dir / Path(relpath).parent
                sub_out.mkdir(parents=True, exist_ok=True)
                res.save_to_json(save_path=str(sub_out))
                res.save_to_markdown(save_path=str(sub_out))
        except Exception as e:
            print(f"  解析失败: {e}")


if __name__ == "__main__":
    main()
