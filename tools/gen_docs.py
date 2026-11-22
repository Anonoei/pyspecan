"""Generate the parts of the documentation that come from the code: API pages and the llms files

    python tools/gen_docs.py             # writes docs/api/*.md, docs/llms.txt, docs/llms-full.txt
    python tools/gen_docs.py --check     # exits 1 if zensical.toml's API nav and the packages disagree

`python tools/builder.py -d` runs this, then `zensical build`. Zensical runs no MkDocs plugins (gen-files), so the pages that
render each package (`::: pyspecan.<pkg>`, mkdocstrings) are written here, one per top-level package; a nested package
gets its own block on its parent's page, so nothing renders twice. The source is read statically (ast, griffe): nothing
is imported, so the tk / web / rpps extras are not needed.

llms.txt (llmstxt.org) lists the pages; llms-full.txt is AGENTS.md, every public package's docstring and a one-line
signature and summary of every public class and function (with the name a plot or marker kind registers under), so an
agent can read the whole library in one file.
"""
import argparse
import ast
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pyspecan"
DOCS = ROOT / "docs"
SITE = "https://anonoei.github.io/pyspecan"

# Top-level packages in the order data runs through them (pyspecan, The data path), then the support packages
ORDER = ["model", "plots", "measure", "controller", "view", "backend", "obj", "utils"]


def public(name):
    return not name.startswith("_")


def packages(top=SRC):
    """Public packages directly below `top`"""
    return sorted(p for p in top.iterdir() if p.is_dir() and public(p.name) and (p / "__init__.py").exists())


def root_modules():
    """The modules of the top-level package itself (specan, arguments, config...): rendered on the pyspecan page"""
    return [f for f in sorted(SRC.glob("*.py")) if public(f.stem)]


def modname(path):
    return ".".join(path.relative_to(SRC.parent).with_suffix("").parts).removesuffix(".__init__")


def own_members(pkg):
    """What a package's own page block renders: its modules and what its __init__ defines (not nested packages)"""
    mods = [f.stem for f in sorted(pkg.glob("*.py")) if public(f.stem)]
    tree = ast.parse((pkg / "__init__.py").read_text(encoding="utf-8"))
    defs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and public(n.name)]
    return mods + defs


def block(pkg):
    members = own_members(pkg)
    lines = [f"::: {modname(pkg / '__init__.py')}", "    options:", "      show_submodules: true"]
    lines.append("      members: " + ("[" + ", ".join(members) + "]" if members else "false"))
    out = ["\n".join(lines)]
    for sub in packages(pkg):
        out += block(sub)
    return out


def first_line(doc):
    """The first paragraph, on one line"""
    para = (doc or "").strip().split("\n\n")[0]
    return " ".join(line.strip() for line in para.split("\n"))


def first_sentence(doc):
    line = first_line(doc)
    m = re.search(r"(?<=[a-z0-9)`])\. ", line)
    return line[:m.start() + 1] if m else line


def docstring(path):
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""


def api_pages(docs=DOCS):
    tops = {p.name: p for p in packages()}
    missing = set(tops) - set(ORDER)
    if missing:
        sys.exit(f"gen_docs: add {sorted(missing)} to ORDER")
    out = docs / "api"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    rows = ["| Package | What it is |", "|---|---|",
            f"| [pyspecan](pyspecan.md) | {first_line(docstring(SRC / '__init__.py'))} |"]
    root = ["::: pyspecan\n    options:\n      members: false"] + [f"::: {modname(m)}" for m in root_modules()]
    (out / "pyspecan.md").write_text("\n\n".join(root) + "\n", encoding="utf-8")
    for name in ORDER:
        pkg = tops[name]
        (out / f"{name}.md").write_text("\n\n".join(block(pkg)) + "\n", encoding="utf-8")
        rows.append(f"| [pyspecan.{name}]({name}.md) | {first_line(docstring(pkg / '__init__.py'))} |")
    (out / "index.md").write_text("# API reference\n\nEvery public package, rendered from its docstrings. The data path "
                                  "and the package map are [pyspecan](pyspecan.md); how plots work is "
                                  "[pyspecan.plots](plots.md).\n\n" + "\n".join(rows) + "\n", encoding="utf-8")


def nav_api():
    """The API pages zensical.toml's nav lists"""
    cfg = tomllib.loads((ROOT / "zensical.toml").read_text(encoding="utf-8"))
    for entry in cfg["project"]["nav"]:
        if "API" in entry:
            return [p if isinstance(p, str) else next(iter(p.values())) for p in entry["API"]]
    return []


def check_nav():
    want = ["api/index.md", "api/pyspecan.md"] + [f"api/{n}.md" for n in ORDER]
    have = nav_api()
    if have != want:
        print("zensical.toml nav API should be:\n" + "\n".join(f'    "{p}",' for p in want))
        return False
    return True


# ---- llms files

def signature(node):
    a = node.args
    names = [x.arg for x in a.posonlyargs + a.args if x.arg not in ("self", "cls")]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        names.append("*")
    names += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return "(" + ", ".join(names) + ")"


def registers(node):
    """` [plot "PSD"]` for a class decorated @plot("PSD") (or @marker_kind("peak")), empty otherwise"""
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in ("plot", "marker_kind") \
                and d.args and isinstance(d.args[0], ast.Constant):
            return f' [{d.func.id.replace("_", " ")} "{d.args[0].value}"]'
    return ""


def summaries(path):
    """`name(args): first docstring line` for each public class and function a module defines"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and public(n.name):
            if isinstance(n, ast.ClassDef):
                init = next((b for b in n.body if isinstance(b, ast.FunctionDef) and b.name == "__init__"), None)
                sig = (signature(init) if init else "") + registers(n)
            else:
                sig = signature(n)
            out.append(f"- {n.name}{sig}: {first_sentence(ast.get_docstring(n))}".rstrip(": "))
    return out


def walk(pkg):
    """Every public module of a package, the package first"""
    yield pkg / "__init__.py"
    for f in sorted(pkg.glob("*.py")):
        if public(f.stem):
            yield f
    for sub in packages(pkg):
        yield from walk(sub)


def pages():
    cfg = tomllib.loads((ROOT / "zensical.toml").read_text(encoding="utf-8"))
    def flat(items, section=""):
        for it in items:
            for title, val in it.items() if isinstance(it, dict) else [(None, it)]:
                if isinstance(val, list):
                    yield from flat(val, title)
                else:
                    yield section, title, val
    return list(flat(cfg["project"]["nav"]))


def h1(path):
    m = re.search(r"^# (.+)$", path.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else path.stem


def page_url(page):
    """The site URL of a docs page: index.md is the root, x/y.md is x/y/"""
    path = re.sub(r"(^|/)index\.md$", r"\1", page)
    return f"{SITE}/" + (path.removesuffix(".md") + "/" if path.endswith(".md") else path)


def llms(docs=DOCS):
    lines = ["# pyspecan", "", "> A spectrum analyzer library in Python: web, tk and console views of samples from files, "
             "radios (pysdrlib) and TCP IQ streams. Toolkit-independent plots (`Plot` turns the shared `Source` into a "
             "`Frame`) that every view draws; layouts from the command line or JSON; DSP plots on the optional rpps.", "",
             f"- [llms-full.txt]({SITE}/llms-full.txt): AGENTS.md, every package docstring and every public signature in one file",
             "- [AGENTS.md](https://github.com/Anonoei/pyspecan/blob/main/AGENTS.md): orientation for agents working on the code", ""]
    groups = {}
    for sec, title, page in pages():
        if page.startswith("api/"):
            continue
        groups.setdefault(sec or "Docs", []).append(f"- [{title or h1(DOCS / page)}]({page_url(page)})")
    for sec, items in groups.items():
        lines += ["", f"## {sec}", ""] + items
    lines += ["", "## API", "", f"- [API reference]({SITE}/api/): every package, rendered from its docstrings",
              f"- [pyspecan]({SITE}/api/pyspecan/): {first_line(docstring(SRC / '__init__.py'))}"]
    for name in ORDER:
        lines.append(f"- [pyspecan.{name}]({SITE}/api/{name}/): {first_line(docstring(SRC / name / '__init__.py'))}")
    (docs / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    full = [(ROOT / "AGENTS.md").read_text(encoding="utf-8").rstrip(), "", "# Package docstrings and public API", "",
            "One section per module: the package's docstring in full, then `name(args): summary` per public class and "
            "function (`[plot \"Name\"]`: what it registers as). Module docstrings other than packages' are summarized "
            "to their first paragraph.", ""]
    mods = [SRC / "__init__.py"] + root_modules() + [m for n in ORDER for m in walk(SRC / n)]
    for path in mods:
        name = modname(path)
        doc = docstring(path)
        full.append(f"## {name}")
        full.append("")
        if path.name == "__init__.py":
            full.append(re.sub(r"^(#+) ", r"#\1 ", doc.strip(), flags=re.M))   # below this module's heading
        elif doc:
            full.append(first_line(doc))
        items = summaries(path)
        if items:
            full += [""] + items
        full.append("")
    (docs / "llms-full.txt").write_text("\n".join(full).rstrip() + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="only check zensical.toml's API nav")
    a = ap.parse_args(argv)
    if a.check:
        sys.exit(0 if check_nav() else 1)
    api_pages()
    llms()
    if not check_nav():
        sys.exit(1)
    print(f"wrote {DOCS / 'api'}, {DOCS / 'llms.txt'}, {DOCS / 'llms-full.txt'}")


if __name__ == "__main__":
    main()
