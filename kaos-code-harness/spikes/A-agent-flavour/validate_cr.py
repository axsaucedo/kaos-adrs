"""Spike A — validate the harness Agent CR against the REAL Agent CRD schema.

No cluster needed: the CRD's OpenAPI v3 schema is committed in the kaos repo at
operator/config/crd/bases/kaos.tools_agents.yaml. Validating against it proves the
claim that matters — that a coding harness is expressible with **no CRD change**.

    uv run --with pyyaml --with jsonschema validate_cr.py [path/to/kaos]
"""

import sys
from pathlib import Path

import jsonschema
import yaml

KAOS = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() /
            ".humanlayer/workspaces/kaos-extension-to-coding-harness/kaos")
CRD = KAOS / "operator/config/crd/bases/kaos.tools_agents.yaml"
CR = Path(__file__).with_name("agent-harness.yaml")


def load_schema():
    doc = yaml.safe_load(CRD.read_text())
    versions = doc["spec"]["versions"]
    v = next((x for x in versions if x.get("storage")), versions[0])
    return v["name"], v["schema"]["openAPIV3Schema"]


def main():
    if not CRD.exists():
        sys.exit(f"CRD not found at {CRD}\nPass the kaos repo path as argv[1].")

    version, schema = load_schema()
    cr = yaml.safe_load(CR.read_text())

    assert cr["apiVersion"].endswith(version), (
        f"CR targets {cr['apiVersion']}, CRD storage version is {version}")

    # Kubernetes prunes unknown fields rather than rejecting them, so an unknown
    # key is a silent no-op, not an error. Check for that explicitly.
    validator = jsonschema.Draft4Validator(schema)
    errors = sorted(validator.iter_errors(cr), key=lambda e: list(e.path))

    print(f"CRD: {CRD.relative_to(KAOS)}")
    print(f"storage version: {version}")
    print(f"CR: {CR.name}\n")

    if errors:
        print(f"INVALID — {len(errors)} error(s):")
        for e in errors:
            print(f"  .{'.'.join(str(p) for p in e.path)}: {e.message[:160]}")
        sys.exit(1)

    # Report which top-level spec fields the schema actually knows about, so a
    # pruned (silently dropped) field cannot masquerade as a passing validation.
    known = set(schema["properties"]["spec"]["properties"])
    used = set(cr["spec"])
    unknown = used - known
    print(f"spec fields used: {', '.join(sorted(used))}")
    if unknown:
        print(f"WOULD BE PRUNED (not in CRD): {', '.join(sorted(unknown))}")
        sys.exit(1)

    # Confirm the specific escape hatches this design leans on really exist.
    for path, label in [
        (("container", "image"), "spec.container.image"),
        (("podSpec",), "spec.podSpec"),
    ]:
        node = schema["properties"]["spec"]["properties"]
        for i, key in enumerate(path):
            node = node[key] if i == 0 else node["properties"][key]
        print(f"  present: {label}")

    ps = schema["properties"]["spec"]["properties"]["podSpec"]["properties"]
    for key in ("initContainers", "volumes", "containers"):
        assert key in ps, f"spec.podSpec.{key} missing"
        print(f"  present: spec.podSpec.{key}")

    co = schema["properties"]["spec"]["properties"]["container"]["properties"]
    print(f"\nContainerOverride fields: {', '.join(sorted(co))}")
    for missing in ("securityContext", "workingDir", "volumeMounts"):
        if missing not in co:
            print(f"  NOT on ContainerOverride (podSpec only): {missing}")

    print("\nVALID — expressible with no CRD change.")


if __name__ == "__main__":
    main()
