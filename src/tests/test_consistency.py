"""Level 3 checks: STEPS, patch files and the tools README agree, and the layout rules hold.

Pure Python; reads only the repository's own source files, never game data.
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tools import apply_all

SRC = Path(__file__).resolve().parents[1]
TOOLS = SRC / "tools"
PATCHES = TOOLS / "patches"
README = (TOOLS / "README.md").read_text(encoding="utf-8")
STEPS = apply_all.STEPS
TEST_AIDS = apply_all.TEST_AIDS

OUR_PACKAGES = ("lib", "patches", "patches/test_aids", "audio", "closecall", "scripts")
# decomp build tooling from the upstream template (and apply_all, which runs as a plain script
# with `python tools/apply_all.py`, so it can't import tools.lib.paths)
UPSTREAM = {"project.py", "download_tool.py", "decompctx.py", "transform_dep.py", "upload_progress.py",
            "ninja_syntax.py"}


def our_files():
    return sorted(p for pkg in OUR_PACKAGES for p in (TOOLS / pkg).glob("*.py"))


def module_name(path):
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


def rel(path):
    return path.relative_to(SRC).as_posix()


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# 1. steps <-> files ---------------------------------------------------------------------------

def test_steps_have_scripts():
    missing = [s for s in STEPS if not (PATCHES / f"apply_{s}_patch.py").exists()]
    missing += [s for s in TEST_AIDS if not (PATCHES / "test_aids" / f"apply_{s}_patch.py").exists()]
    assert missing == []


def test_every_script_is_a_step():
    def names(folder):
        return {p.name[len("apply_"):-len("_patch.py")] for p in folder.glob("apply_*_patch.py")}
    assert names(PATCHES) - set(STEPS) == set()
    assert names(PATCHES / "test_aids") - set(TEST_AIDS) == set()


def test_no_duplicate_steps():
    everything = STEPS + TEST_AIDS
    assert len(everything) == len(set(everything))


# 2. --list ------------------------------------------------------------------------------------

def test_apply_all_list():
    out = subprocess.run([sys.executable, "tools/apply_all.py", "--list"], cwd=SRC, capture_output=True,
                         text=True, check=True).stdout
    assert out.split() == STEPS
    out = subprocess.run([sys.executable, "tools/apply_all.py", "--list", "--only", "unlucky", "dk_split"],
                         cwd=SRC, capture_output=True, text=True, check=True).stdout
    assert out.split() == ["dk_split", "unlucky"]


# 3. every module imports, without touching the filesystem -------------------------------------

IMPORT_PROBE = r"""
import builtins, importlib, json, os, pathlib, sys
results = {}
current = [None]
def guard(name, real):
    def wrapper(*args, **kwargs):
        if current[0]:
            results.setdefault(current[0], []).append(f"{name}{args[:1]!r}")
        return real(*args, **kwargs)
    return wrapper
builtins.open = guard("open", builtins.open)
os.listdir = guard("listdir", os.listdir)
os.scandir = guard("scandir", os.scandir)
for attr in ("open", "read_bytes", "read_text", "write_bytes", "write_text", "iterdir", "glob", "mkdir"):
    setattr(pathlib.Path, attr, guard(attr, getattr(pathlib.Path, attr)))
for name in json.loads(sys.argv[1]):
    current[0] = name
    try:
        importlib.import_module(name)
        results.setdefault(name, [])
    except BaseException as e:
        results[name] = [f"import failed: {e!r}"]
    current[0] = None
print(json.dumps(results))
"""
MODULES = [module_name(p) for p in our_files() if p.name != "__init__.py"]


@pytest.fixture(scope="module")
def import_report():
    proc = subprocess.run([sys.executable, "-c", IMPORT_PROBE, json.dumps(MODULES)], cwd=SRC,
                          capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_cleanly(import_report, module):
    assert import_report[module] == []


# 4. patch shape -------------------------------------------------------------------------------

PATCH_FILES = sorted(PATCHES.glob("apply_*_patch.py")) + sorted((PATCHES / "test_aids").glob("apply_*_patch.py"))


def has_main_guard(tree):
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left, right = node.test.left, node.test.comparators[0]
            if isinstance(left, ast.Name) and left.id == "__name__" and getattr(right, "value", None) == "__main__":
                return True
    return False


@pytest.mark.parametrize("path", PATCH_FILES, ids=lambda p: p.stem)
def test_patch_shape(path):
    tree = parse(path)
    assert ast.get_docstring(tree), "module docstring"
    assert has_main_guard(tree), 'if __name__ == "__main__":'
    assert any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body), "def main"


# 5./6. README dependency table and bundles ----------------------------------------------------

def table(heading):
    """Rows (lists of cells) of the first markdown table after `heading`."""
    section = README.split(heading, 1)[1]
    rows = []
    for line in section.splitlines():
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows:
            break
    return [r for r in rows[2:]]      # drop the header and the --- row


def ticked(cell):
    return re.findall(r"`([^`]+)`", cell)


DEPENDENCY_ROWS = table("### Dependency table")
NEEDS = {}
for _row in DEPENDENCY_ROWS:
    for _step in ticked(_row[0]):
        NEEDS.setdefault(_step, []).append(ticked(_row[1]))


def test_dependency_table_lists_every_step_once():
    assert sorted(NEEDS) == sorted(STEPS)
    assert {s: len(v) for s, v in NEEDS.items() if len(v) != 1} == {}


@pytest.mark.parametrize("step", STEPS)
def test_needs_come_first(step):
    for need in NEEDS.get(step, [[]])[0]:
        assert need in STEPS, f"{need} is not a step"
        assert STEPS.index(need) < STEPS.index(step), f"{need} must run before {step}"


def closure(steps):
    out, todo = set(), list(steps)
    while todo:
        s = todo.pop()
        if s not in out:
            out.add(s)
            todo += NEEDS[s][0]
    return out


def bundles():
    found = {}
    for name, command, _ in table("### Bundles"):
        match = re.fullmatch(r"`--only ([a-z0-9_ ]+)`", command)
        if match:
            found[name] = match.group(1).split()
    # the Unlucky Star row is prose: "the E. Gadd's Garage steps plus `random_bonus minigame_wins unlucky`"
    unlucky = [r for r in table("### Bundles") if r[0] == "Unlucky Star"]
    assert unlucky and "E. Gadd's Garage steps plus" in unlucky[0][1]
    found["Unlucky Star"] = found["E. Gadd's Garage"] + ticked(unlucky[0][1])[0].split()
    return found


BUNDLES = bundles()


def test_bundles_parsed():
    assert len(BUNDLES) == len(table("### Bundles"))


@pytest.mark.parametrize("name", sorted(BUNDLES))
def test_bundle_is_closed_under_needs(name):
    steps = BUNDLES[name]
    assert [s for s in steps if s not in STEPS] == []
    assert sorted(closure(steps) - set(steps)) == []


# 7. layout rules from AGENTS.md ---------------------------------------------------------------

def test_no_dunder_file_paths():
    allowed = {"tools/lib/paths.py", "tools/apply_all.py"} | {f"tools/{n}" for n in UPSTREAM}
    offenders = []
    for path in sorted(TOOLS.rglob("*.py")):
        if rel(path) in allowed or "bin" in path.relative_to(TOOLS).parts:
            continue
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Name) and node.id == "__file__":
                offenders.append(f"{rel(path)}:{node.lineno}")
    assert offenders == []


def test_no_parent_relative_path_strings():
    offenders = []
    for path in our_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "../" in node.value:
                # docstrings and messages may mention a relative path; flag only path-like literals
                if not any(ch.isspace() for ch in node.value):
                    offenders.append(f"{rel(path)}:{node.lineno} {node.value!r}")
    assert offenders == []


def lib_objects():
    """id -> "tools.lib.module.name" for every function and class defined in tools.lib."""
    import importlib
    import inspect
    found = {}
    for path in sorted((TOOLS / "lib").glob("*.py")):
        module = importlib.import_module(module_name(path))
        for name, obj in vars(module).items():
            if (inspect.isfunction(obj) or inspect.isclass(obj)) and obj.__module__ == module.__name__:
                found[id(obj)] = f"{module.__name__}.{name}"
    return found


def test_lib_helpers_are_not_imported_through_patches():
    # A patch may export its own helpers (a wrapper with its bank as defaults, its own caves),
    # even under a name tools.lib also uses. What it must not do is pass a tools.lib helper
    # through: those must be imported from tools.lib. Compared by object identity, not by name.
    import importlib
    lib = lib_objects()
    offenders = []
    for path in sorted(TOOLS.rglob("*.py")):
        if "bin" in path.relative_to(TOOLS).parts:
            continue
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tools.patches"):
                module = importlib.import_module(node.module)
                for alias in node.names:
                    obj = getattr(module, alias.name, None)
                    if obj is not None and id(obj) in lib:
                        offenders.append(f"{rel(path)}:{node.lineno} {alias.name} from {node.module} "
                                         f"(is {lib[id(obj)]})")
    assert offenders == []


# 8. assets referenced exist -------------------------------------------------------------------

OPTIONAL_ASSETS = {
    "closecall_instpic.png",   # optional screenshot override, checked with .exists() (closecall_assets.py)
}


def asset_literals():
    found = []
    for path in sorted(TOOLS.rglob("*.py")):
        for node in ast.walk(parse(path)):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
                    and isinstance(node.left, ast.Name) and node.left.id == "ASSETS"
                    and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
                found.append((rel(path), node.lineno, node.right.value))
    return found


def test_asset_literals_found():
    assert len(asset_literals()) >= 3


@pytest.mark.parametrize("where, line, name", asset_literals(), ids=lambda v: str(v))
def test_asset_exists(where, line, name):
    if name in OPTIONAL_ASSETS:
        pytest.skip("optional asset")
    assert (TOOLS / "assets" / name).is_file()


def test_capsule_assets_exist():
    from tools.patches import apply_star_trap_orb_patch
    for name in apply_star_trap_orb_patch.CAPSULE_NEW_ENTRIES:
        assert (TOOLS / "assets" / name).is_file()
