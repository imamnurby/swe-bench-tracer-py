import argparse
import ast
import json
import re

from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

"""
Given:
  1) A JSONL file produced by the tracer (each line: {"target": ..., "stack": ...}),
  2) A unified diff patch file, and
  3) A repository root,

the script:

  • Parses the patch to find which functions/classes (module:qualname) were modified
    on the chosen side of the diff (old or new).
  • Uses those modified qualnames as targets to filter the tracer JSONL.
  • Computes the union of all function qualnames that appear in any stack for those targets.
  • Writes the resulting sorted list of qualnames to a JSON file.
"""


def extract_modified_lines(patch_content: str) -> Dict[str, Dict[str, List[int]]]:
    """
    Parses a patch file content and extracts added/removed line numbers per file.

    Returns:
        {
            "added": {
                "path/to/file.py": [line_no1, line_no2, ...],
                ...
            },
            "removed": {
                "path/to/file.py": [line_no1, line_no2, ...],
                ...
            },
        }
    """
    # File headers: --- a/<path>\n+++ b/<path>\n  (a/ and b/ optional)
    file_header_pattern = re.compile(r'--- (?:a/)?(.*?)\n\+\+\+ (?:b/)?(.*?)\n')

    # Hunk headers: @@ -<old_start>[,<old_count>] +<new_start>[,<new_count>] @@<context>\n
    hunk_header_pattern = re.compile(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*?)\n')

    added: Dict[str, List[int]] = defaultdict(list)
    removed: Dict[str, List[int]] = defaultdict(list)

    # Split by "diff --git ..." blocks; the first element is before the first diff
    file_patches = patch_content.split('diff --git ')[1:]
    for file_patch in file_patches:
        file_header_match = file_header_pattern.search(file_patch)
        if not file_header_match:
            continue

        old_path = file_header_match.group(1)  # path before change
        new_path = file_header_match.group(2)  # path after change

        hunks_iter = list(hunk_header_pattern.finditer(file_patch))
        split_parts = hunk_header_pattern.split(file_patch)[1:]

        # pattern has 3 capturing groups; for match i, the body sits at index (i*4)+3
        for i, h in enumerate(hunks_iter):
            removal_start = int(h.group(1))
            addition_start = int(h.group(2))

            hunk_body_index = (i * 4) + 3
            if hunk_body_index >= len(split_parts):
                continue
            hunk_body = split_parts[hunk_body_index]

            old_line_num = removal_start
            new_line_num = addition_start
            removal_line_numbers: List[int] = []
            addition_line_numbers: List[int] = []

            for line in hunk_body.split('\n'):
                if not line:
                    continue
                if line.startswith('-'):
                    # Removed line
                    removal_line_numbers.append(old_line_num)
                    old_line_num += 1
                elif line.startswith('+'):
                    # Added line
                    addition_line_numbers.append(new_line_num)
                    new_line_num += 1
                elif line.startswith(' '):
                    # Context line
                    old_line_num += 1
                    new_line_num += 1
                else:
                    # Should not happen in a normal unified diff, ignore
                    pass

            if addition_line_numbers:
                added[new_path].extend(addition_line_numbers)
            if removal_line_numbers:
                removed[old_path].extend(removal_line_numbers)

    added_sorted = {path: sorted(set(nums)) for path, nums in added.items() if nums}
    removed_sorted = {path: sorted(set(nums)) for path, nums in removed.items() if nums}

    return {
        "added": added_sorted,
        "removed": removed_sorted,
    }


class _DefCollector(ast.NodeVisitor):
    """
    Collects class/function definitions with their [start, end] line ranges
    and qualnames (relative to the module).
    """

    def __init__(self) -> None:
        self.stack: List[str] = []  # name components for qualname
        # entries: (start_lineno, end_lineno, qualname)
        self.defs: List[Tuple[int, int, str]] = []

    def _record_def(self, node: ast.AST, name: str) -> None:
        qualname = ".".join(self.stack + [name]) if self.stack else name
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if start is None:
            return
        if end is None:
            # Fallback if end_lineno is not present (older Python)
            end = start
        self.defs.append((start, end, qualname))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record_def(node, node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_def(node, node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_def(node, node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def _path_to_module_name(repo_root: Path, file_path: str) -> str:
    """
    Convert a repo-relative file path like 'astropy/modeling/separable.py'
    into a module name like 'astropy.modeling.separable'.

    This is a heuristic to match the module name used by your tracer.
    """
    p = Path(file_path)

    try:
        rel = p.relative_to(repo_root)
    except ValueError:
        rel = p

    parts = list(rel.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]  # strip .py

    # Remove empty parts, join with '.'
    parts = [p for p in parts if p]
    return ".".join(parts) if parts else "<unknown_module>"


def _find_qualname_for_line(
    defs: List[Tuple[int, int, str]], line_no: int
) -> str:
    """
    Given a list of (start, end, qualname) and a line number,
    return the innermost definition that contains the line, if any.

    If no definition contains the line, returns an empty string.
    """
    candidates = [
        (start, end, q)
        for (start, end, q) in defs
        if start <= line_no <= end
    ]
    if not candidates:
        return ""
    # Innermost = the one with the largest start line
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][2]


def extract_modified_qualnames(
    patch_content: str,
    repo_root: str,
    mode: str = "new",
) -> List[str]:
    """
    Given a unified diff patch content and a repo root, extract the full
    qualified names ('module:qualname') of classes/functions whose bodies
    include at least one modified line.

    mode:
      - "new": use added lines and file paths from the NEW version
               (i.e. line_info["added"] / new_path).
               repo_root should point to the NEW checkout.
      - "old": use removed lines and file paths from the OLD version
               (i.e. line_info["removed"] / old_path).
               repo_root should point to the OLD checkout.
    Returns:
      Sorted list of strings: "<module>:<qualname>".
    """
    mode = mode.lower()
    if mode not in {"new", "old"}:
        raise ValueError(f"Unsupported mode: {mode!r}. Use 'new' or 'old'.")

    repo_root_path = Path(repo_root)
    line_info = extract_modified_lines(patch_content)

    modified_qualnames: Set[str] = set()

    def _process(path_to_lines: Dict[str, List[int]]) -> None:
        for rel_path, lines in path_to_lines.items():
            file_on_disk = repo_root_path / rel_path
            source = file_on_disk.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_on_disk))

            collector = _DefCollector()
            collector.visit(tree)

            module_name = _path_to_module_name(repo_root_path, str(file_on_disk))

            for line_no in lines:
                local_qualname = _find_qualname_for_line(collector.defs, line_no)
                if local_qualname:
                    full_qualname = f"{module_name}:{local_qualname}"
                    modified_qualnames.add(full_qualname)
                else:
                    # Exclude module level line for now
                    # full_qualname = f"{module_name}:<module>"
                    # modified_qualnames.add(full_qualname)
                    pass

    if mode in {"new", "both"}:
        _process(line_info["added"])

    if mode in {"old", "both"}:
        _process(line_info["removed"])

    return sorted(modified_qualnames)



def load_jsonl(path: str) -> Iterable[dict]:
    """Yield JSON objects, one per line, from a JSONL file."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def collect_functions_by_target(
    jsonl_path: str, target_qualnames: Iterable[str]
) -> Dict[str, Set[str]]:
    """
    For each target qualname, collect the union of all function qualnames
    that appear in stacks for that target.

    Returns:
        dict: target_qualname -> set of function qualnames
    """
    targets_set: Set[str] = set(target_qualnames)
    results: Dict[str, Set[str]] = defaultdict(set)

    for entry in load_jsonl(jsonl_path):
        target = entry.get("target")
        if target not in targets_set:
            continue

        stack = entry.get("stack") or []
        for frame in stack:
            _, qualname = frame[0], frame[1]
            results[target].add(qualname)
    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Parse a patch file and compute the list of modified function/class "
            "qualified names (module:qualname)."
        )
    )
    parser.add_argument(
        "jsonl_path",
        help="Path to the JSONL file produced by the tracer.",
    )
    parser.add_argument(
        "patch_file",
        help="Path to the patch file",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help=(
            "Path to the repository root used to resolve modules/files. "
            "Defaults to current directory."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["new", "old"],
        default="old",
        help=(
            "Which side of the patch to analyze: "
            "'new' for added lines, 'old' for removed lines"
        ),
    )
    parser.add_argument(
        "--output-json",
        dest="output_json",
        required=False,
        help=(
            "Path to write a JSON file containing the sorted list of qualnames. "
            "If omitted, results are only printed to stdout."
        ),
    )

    args = parser.parse_args()

    patch_path = Path(args.patch_file)
    patch_content = patch_path.read_text(encoding="utf-8")

    qualnames = extract_modified_qualnames(
        patch_content=patch_content,
        repo_root=args.repo_root,
        mode=args.mode,
    )


    per_target = collect_functions_by_target(args.jsonl_path, qualnames)

    global_union: Set[str] = set()
    for qname_set in per_target.values():
        global_union.update(qname_set)

    output_obj = sorted(list(global_union))
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(output_obj, f, indent=2, sort_keys=True)
    print(f"JSON files written to {args.output_json}")

if __name__ == "__main__":
    main()
