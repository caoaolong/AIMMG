"""脚本工具函数。"""

from pathlib import Path
from typing import Union


def scan_files(
    root: Union[str, Path],
    suffix: Union[str, list[str]],
    *,
    recursive: bool = True,
) -> list[dict]:
    """
    扫描指定路径下所有指定后缀的文件。

    Args:
        root: 根目录路径。
        suffix: 后缀，如 ".json" 或 [".json", ".py"]。可带或不带点号。
        recursive: 是否递归子目录，默认 True。

    Returns:
        列表，每项为 {"name": 文件名, "relpath": 相对于 root 的路径}。
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return []
    if isinstance(suffix, str):
        suffix = [suffix]
    suffixes = [s if s.startswith(".") else f".{s}" for s in suffix]
    result = []
    it = root.rglob("*") if recursive else root.iterdir()
    for p in it:
        if not p.is_file():
            continue
        if p.suffix.lower() not in [s.lower() for s in suffixes]:
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        result.append({"name": p.name, "relpath": rel.as_posix()})
    return result
