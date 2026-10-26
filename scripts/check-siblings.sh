#!/usr/bin/env bash
# Sibling proof for ADR-0006: xippios-usda-gats, xippios-usda-psd and xippios-usda-nass
# install side by side in one clean environment as portions of the PEP 420 namespaces
# xippios and xippios.usda.
#
# Builds this package's wheel, installs it with xippios-usda-psd and xippios-usda-nass
# into a fresh virtual environment, imports all three, checks that this package's
# reference data ships, runs `uv pip check`, and fails if either namespace level gained
# an __init__.py in site-packages. Run from anywhere: scripts/check-siblings.sh
#
# xippios-usda-esr joins as a third sibling once its scaffold PR merges (its main holds
# only the licence today): add
#   esr="${ESR_REQUIREMENT:-xippios-usda-esr @ git+https://github.com/xippios/sdk-usda-esr@main}"
# to the requirements below and `import xippios.usda.esr` to the check.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
unset VIRTUAL_ENV  # never install into whatever environment the shell has active

# xippios-usda-psd is on PyPI; xippios-usda-nass is not yet, so it comes from git main.
# Switch nass to "xippios-usda-nass" once it is tagged and published (/release-prep);
# PSD_REQUIREMENT and NASS_REQUIREMENT override either.
psd="${PSD_REQUIREMENT:-xippios-usda-psd}"
nass="${NASS_REQUIREMENT:-xippios-usda-nass @ git+https://github.com/xippios/sdk-usda-nass@main}"

cd "$root"
uv build --wheel --out-dir "$work/dist"
uv venv --python "${PYTHON:-3.12}" "$work/venv"
python="$work/venv/bin/python"
# Inert today: pyproject.toml has no [tool.uv.sources], so core resolves from PyPI through
# the wheel's bound and $core stays empty. Kept for a development pin of core
# (conventions §12): while pyproject.toml pins xippios-core there, the wheel needs core
# from that pin too, which the bound alone would not fetch.
core="$("$python" - "$root/pyproject.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as file:
    pin = tomllib.load(file).get("tool", {}).get("uv", {}).get("sources", {}).get("xippios-core")
if isinstance(pin, dict) and "git" in pin:
    ref = next((pin[key] for key in ("rev", "tag", "branch") if key in pin), None)
    print(f"xippios-core @ git+{pin['git']}" + (f"@{ref}" if ref else ""))
PY
)"
if [ -n "$core" ]; then
  echo "xippios-core from the git pin in pyproject.toml: $core"
fi
uv pip install --python "$python" "$work"/dist/*.whl "$psd" "$nass" ${core:+"$core"}

"$python" - <<'PY'
from importlib.metadata import version

import xippios.usda.gats
import xippios.usda.nass
import xippios.usda.psd
from xippios.usda.gats.params import PACKAGED_LISTS, packaged_values

assert all(packaged_values(name) is not None for name in PACKAGED_LISTS), "reference data"
print(
    "imported xippios.usda.gats",
    xippios.usda.gats.__version__,
    "with xippios.usda.psd",
    version("xippios-usda-psd"),
    "and xippios.usda.nass",
    version("xippios-usda-nass"),
    "on xippios-core",
    version("xippios-core"),
)
PY
uv pip check --python "$python"

site="$("$python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
for level in xippios xippios/usda; do
  if [ -e "$site/$level/__init__.py" ]; then
    echo "error: $site/$level/__init__.py exists; $level must stay a namespace portion" >&2
    exit 1
  fi
done
echo "ok: no __init__.py at xippios/ or xippios/usda/ in $site"
