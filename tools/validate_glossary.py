#!/usr/bin/env python3
"""Parse and validate the dlt SKOS glossary (Turtle format).

Usage:
    python tools/validate_glossary.py                          # validate glossary structure
    python tools/validate_glossary.py --check-skills [toolkit] # check skill names against glossary
    python tools/validate_glossary.py --dump                   # dump all concepts as table
    python tools/validate_glossary.py --dump-overlay <toolkit> # dump overlay concepts

Checks:
- TTL file parses without errors
- Every Concept has prefLabel and definition
- Broader/narrower relationships are symmetric
- hiddenLabel (deprecated terms) don't appear as prefLabel elsewhere
- ConceptScheme hasTopConcept references resolve
- Collections reference existing concepts
- Toolkit overlays parse and resolve against base glossary
- Skill names decompose into valid action-object pairs (--check-skills)
"""

import re
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, SKOS

DLT = Namespace("https://dlthub.com/vocab/")

GLOSSARY_PATH = Path(".vocabulary/vocabulary.skos.ttl")
WORKBENCH = Path("workbench")
OVERLAY_GLOB = ".vocabulary/vocabulary.skos.ttl"


def load_graph(path: Path) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def get_concepts(g: Graph) -> set[URIRef]:
    return set(g.subjects(RDF.type, SKOS.Concept))


def get_collections(g: Graph) -> set[URIRef]:
    return set(g.subjects(RDF.type, SKOS.Collection))


def load_overlay(toolkit_path: Path) -> Graph | None:
    """Load a toolkit's SKOS overlay if it exists."""
    overlay_path = toolkit_path / OVERLAY_GLOB
    if not overlay_path.exists():
        return None
    g = Graph()
    g.parse(overlay_path, format="turtle")
    return g


def get_overlay_accepted_alts(overlay: Graph | None) -> set[str]:
    """Extract terms promoted from hiddenLabel to altLabel via exactMatch overlay concepts."""
    if overlay is None:
        return set()

    accepted: set[str] = set()
    for concept in get_concepts(overlay):
        # Only concepts that exactMatch a base concept (i.e., overrides)
        matches = list(overlay.objects(concept, SKOS.exactMatch))
        if not matches:
            continue
        # Collect altLabels on the overlay concept — these override hiddenLabels on the base
        for alt in overlay.objects(concept, SKOS.altLabel):
            accepted.add(str(alt).lower())
    return accepted


def get_overlay_deprecated(overlay: Graph | None) -> dict[str, str]:
    """Extract deprecated toolkit terms (owl:deprecated true)."""
    if overlay is None:
        return {}

    deprecated: dict[str, str] = {}
    for concept in get_concepts(overlay):
        is_deprecated = (concept, OWL.deprecated, Literal(True)) in overlay
        if not is_deprecated:
            continue
        pref = next(overlay.objects(concept, SKOS.prefLabel), None)
        defn = next(overlay.objects(concept, SKOS.definition), None)
        if pref:
            deprecated[str(pref)] = str(defn) if defn else "(no definition)"
    return deprecated


def get_overlay_deprecated_labels(overlay: Graph | None) -> set[str]:
    """Get all labels (pref + alt) of deprecated overlay concepts for scanning."""
    if overlay is None:
        return set()

    labels: set[str] = set()
    for concept in get_concepts(overlay):
        is_deprecated = (concept, OWL.deprecated, Literal(True)) in overlay
        if not is_deprecated:
            continue
        for pref in overlay.objects(concept, SKOS.prefLabel):
            labels.add(str(pref).lower())
        for alt in overlay.objects(concept, SKOS.altLabel):
            labels.add(str(alt).lower())
    return labels


def get_overlay_terms(overlay: Graph | None) -> dict[str, str]:
    """Extract toolkit-specific terms (non-override, non-deprecated concepts)."""
    if overlay is None:
        return {}

    terms: dict[str, str] = {}
    for concept in get_concepts(overlay):
        matches = list(overlay.objects(concept, SKOS.exactMatch))
        if matches:
            continue  # This is an override, not a new term
        is_deprecated = (concept, OWL.deprecated, Literal(True)) in overlay
        if is_deprecated:
            continue
        pref = next(overlay.objects(concept, SKOS.prefLabel), None)
        defn = next(overlay.objects(concept, SKOS.definition), None)
        if pref:
            terms[str(pref)] = str(defn) if defn else "(no definition)"
    return terms


def validate_structure(g: Graph) -> list[str]:
    """Validate glossary internal consistency."""
    errors: list[str] = []
    concepts = get_concepts(g)

    # Every concept must have prefLabel and definition
    for c in sorted(concepts, key=str):
        local = str(c).split("/")[-1]
        pref_labels = list(g.objects(c, SKOS.prefLabel))
        if not pref_labels:
            errors.append(f"  {local}: missing skos:prefLabel")
        definitions = list(g.objects(c, SKOS.definition))
        if not definitions:
            errors.append(f"  {local}: missing skos:definition")

    # Check broader/narrower symmetry
    for s, o in g.subject_objects(SKOS.broader):
        if (o, SKOS.narrower, s) not in g:
            s_local = str(s).split("/")[-1]
            o_local = str(o).split("/")[-1]
            errors.append(f"  {s_local} skos:broader {o_local} but reverse skos:narrower missing")

    for s, o in g.subject_objects(SKOS.narrower):
        if (o, SKOS.broader, s) not in g:
            s_local = str(s).split("/")[-1]
            o_local = str(o).split("/")[-1]
            errors.append(f"  {s_local} skos:narrower {o_local} but reverse skos:broader missing")

    # hiddenLabel should not appear as prefLabel on another concept
    all_pref = {str(label) for label in g.objects(predicate=SKOS.prefLabel)}
    for c in sorted(concepts, key=str):
        for hidden in g.objects(c, SKOS.hiddenLabel):
            h = str(hidden)
            if h in all_pref:
                c_local = str(c).split("/")[-1]
                errors.append(f"  {c_local}: hiddenLabel '{h}' is also a prefLabel (conflict)")

    # ConceptScheme topConcepts resolve
    for scheme in g.subjects(RDF.type, SKOS.ConceptScheme):
        for top in g.objects(scheme, SKOS.hasTopConcept):
            if top not in concepts:
                errors.append(f"  hasTopConcept {top} not found as Concept")

    # Collection members resolve
    for coll in get_collections(g):
        coll_label = next(g.objects(coll, SKOS.prefLabel), str(coll))
        for member in g.objects(coll, SKOS.member):
            if member not in concepts:
                m_local = str(member).split("/")[-1]
                errors.append(f"  Collection '{coll_label}' references unknown concept: {m_local}")

    return errors


def validate_overlay(base: Graph, overlay: Graph, toolkit_name: str) -> list[str]:
    """Validate an overlay against the base glossary."""
    errors: list[str] = []
    base_concepts = get_concepts(base)

    for concept in sorted(get_concepts(overlay), key=str):
        local = str(concept).split("/")[-1]

        # Concepts with exactMatch must point to a real base concept
        for match in overlay.objects(concept, SKOS.exactMatch):
            if match not in base_concepts:
                m_local = str(match).split("/")[-1]
                errors.append(f"  {local}: exactMatch '{m_local}' not found in base glossary")

        # altLabels promoted via exactMatch should actually be hiddenLabels in base
        matches = list(overlay.objects(concept, SKOS.exactMatch))
        if matches:
            base_concept = matches[0]
            base_hidden = {str(h).lower() for h in base.objects(base_concept, SKOS.hiddenLabel)}
            for alt in overlay.objects(concept, SKOS.altLabel):
                alt_str = str(alt).lower()
                if alt_str not in base_hidden:
                    base_alt = {str(a).lower() for a in base.objects(base_concept, SKOS.altLabel)}
                    if alt_str not in base_alt:
                        pref = str(next(base.objects(base_concept, SKOS.prefLabel), ""))
                        if alt_str != pref.lower():
                            errors.append(
                                f"  {local}: altLabel '{alt}' is not a hiddenLabel"
                                f" on base concept '{pref}' — nothing to override"
                            )

        # Check prefLabel and definition exist
        if not list(overlay.objects(concept, SKOS.prefLabel)):
            errors.append(f"  {local}: missing skos:prefLabel")
        if not list(overlay.objects(concept, SKOS.definition)):
            # Allow override concepts (exactMatch) to skip definition
            if not matches:
                errors.append(f"  {local}: missing skos:definition")

    return errors


def extract_actions(g: Graph) -> dict[str, list[str]]:
    """Extract canonical action -> valid objects from action concepts."""
    actions: dict[str, list[str]] = {}
    for c in get_concepts(g):
        local = str(c).split("/")[-1]
        if not local.startswith("action-"):
            continue
        action_name = str(next(g.objects(c, SKOS.prefLabel)))
        defn = str(next(g.objects(c, SKOS.definition), ""))
        # Parse "Valid objects: X, Y, Z." from definition
        m = re.search(r"Valid objects?:\s*([^.]+)", defn)
        if m:
            objects = [o.strip() for o in m.group(1).split(",")]
            actions[action_name] = objects
        else:
            actions[action_name] = []
    return actions


def check_skill_names(g: Graph, toolkit_path: Path) -> list[str]:
    """Check skill names against canonical action-object pairs."""
    issues: list[str] = []
    actions = extract_actions(g)

    skills_dir = toolkit_path / "skills"
    if not skills_dir.exists():
        issues.append(f"  No skills/ directory in {toolkit_path}")
        return issues

    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        # Parse name from frontmatter
        text = skill_md.read_text()
        m = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        if not m:
            issues.append(f"  {skill_dir.name}: no name in frontmatter")
            continue

        name = m.group(1).strip()
        # Decompose: first token is action, rest is object
        parts = name.split("-", 1)
        if len(parts) < 2:
            issues.append(f"  {name}: cannot decompose into <action>-<object>")
            continue

        action = parts[0]
        obj = parts[1]

        # Check action
        if action not in actions:
            closest = _suggest_action(action, actions)
            hint = f" (did you mean '{closest}'?)" if closest else ""
            issues.append(f"  {name}: unknown action '{action}'{hint}")
        else:
            # Check object against valid objects for this action
            valid = actions[action]
            if valid and not _object_matches(obj, valid):
                issues.append(
                    f"  {name}: object '{obj}' not valid for '{action}'"
                    f" (valid: {', '.join(valid)})"
                )

    return issues


def _object_matches(obj: str, valid: list[str]) -> bool:
    """Fuzzy match object name against valid objects list."""
    obj_normalized = obj.replace("-", " ").lower()
    for v in valid:
        v_normalized = v.strip().lower()
        # Exact or substring match
        if obj_normalized == v_normalized or v_normalized in obj_normalized:
            return True
        # Singular/plural
        if obj_normalized.rstrip("s") == v_normalized.rstrip("s"):
            return True
    return False


def _suggest_action(action: str, actions: dict[str, list[str]]) -> str | None:
    """Suggest closest canonical action."""
    synonyms: dict[str, str] = {
        "new": "add",
        "build": "create",
        "make": "create",
        "generate": "create",
        "view": "show",
        "explore": "inspect",
        "execute": "run",
        "trigger": "run",
        "start": "run",
        "troubleshoot": "debug",
        "diagnose": "debug",
        "verify": "validate",
        "check": "validate",
        "test": "validate",
        "examine": "inspect",
        "review": "inspect",
        "harden": "adjust",
        "setup": "create",
        "prepare": "create",
        "improve": "maintain",
    }
    return synonyms.get(action)


def dump_concepts(g: Graph) -> None:
    """Print all concepts as a readable table."""
    concepts = get_concepts(g)
    rows: list[tuple[str, str, str, str, str]] = []

    for c in sorted(concepts, key=str):
        local = str(c).split("/")[-1]
        pref = str(next(g.objects(c, SKOS.prefLabel), ""))
        alts = ", ".join(str(a) for a in g.objects(c, SKOS.altLabel))
        hidden = ", ".join(str(h) for h in g.objects(c, SKOS.hiddenLabel))
        broader = ", ".join(str(b).split("/")[-1] for b in g.objects(c, SKOS.broader))
        rows.append((local, pref, alts, hidden, broader))

    # Print
    print(f"{'ID':<30} {'prefLabel':<25} {'altLabels':<30} {'hiddenLabels':<35} {'broader':<20}")
    print("-" * 140)
    for row in rows:
        print(f"{row[0]:<30} {row[1]:<25} {row[2]:<30} {row[3]:<35} {row[4]:<20}")
    print(f"\n{len(rows)} concepts total")


def dump_overlay(overlay: Graph, toolkit_name: str) -> None:
    """Print overlay contents: accepted alternatives, deprecated, and toolkit-specific terms."""
    accepted = get_overlay_accepted_alts(overlay)
    deprecated = get_overlay_deprecated(overlay)
    terms = get_overlay_terms(overlay)

    print(f"\nOverlay: {toolkit_name}")

    if accepted:
        print(f"\n  Accepted alternatives ({len(accepted)}):")
        for alt in sorted(accepted):
            print(f"    {alt}")

    if deprecated:
        print(f"\n  Deprecated terms ({len(deprecated)}):")
        for term, defn in sorted(deprecated.items()):
            short_defn = defn[:80] + "..." if len(defn) > 80 else defn
            print(f"    {term:<25} {short_defn}")

    if terms:
        print(f"\n  Toolkit-specific terms ({len(terms)}):")
        for term, defn in sorted(terms.items()):
            short_defn = defn[:80] + "..." if len(defn) > 80 else defn
            print(f"    {term:<25} {short_defn}")

    if not accepted and not deprecated and not terms:
        print("  (empty overlay)")


def main() -> None:
    args = sys.argv[1:]
    do_dump = "--dump" in args
    do_dump_overlay = "--dump-overlay" in args
    do_check = "--check-skills" in args

    if not GLOSSARY_PATH.exists():
        print(f"ERROR: glossary not found at {GLOSSARY_PATH}")
        sys.exit(1)

    # Parse base glossary
    print(f"Parsing {GLOSSARY_PATH}...")
    try:
        g = load_graph(GLOSSARY_PATH)
    except Exception as e:
        print(f"PARSE ERROR: {e}")
        sys.exit(1)

    concepts = get_concepts(g)
    collections = get_collections(g)
    triples = len(g)
    print(f"  {triples} triples, {len(concepts)} concepts, {len(collections)} collections")

    if do_dump:
        print()
        dump_concepts(g)
        return

    # Validate base structure
    print("\nValidating glossary structure...")
    errors = validate_structure(g)
    if errors:
        print(f"  {len(errors)} issues:")
        for e in errors:
            print(e)
    else:
        print("  All checks passed")

    # Extract and display canonical actions
    actions = extract_actions(g)
    if actions:
        print(f"\nCanonical actions ({len(actions)}):")
        for action, objects in sorted(actions.items()):
            objs = ", ".join(objects) if objects else "(any)"
            print(f"  {action} -> {objs}")

    # Discover and validate all overlays
    overlay_errors: list[str] = []
    overlay_map: dict[str, Graph] = {}  # toolkit name -> overlay graph
    for toolkit_dir in sorted(WORKBENCH.iterdir()):
        if not toolkit_dir.is_dir():
            continue
        overlay = load_overlay(toolkit_dir)
        if overlay is None:
            continue
        overlay_map[toolkit_dir.name] = overlay
        overlay_concepts = get_concepts(overlay)
        overlay_triples = len(overlay)
        print(f"\nOverlay: {toolkit_dir.name} ({overlay_triples} triples, {len(overlay_concepts)} concepts)")

        ov_errors = validate_overlay(g, overlay, toolkit_dir.name)
        if ov_errors:
            print(f"  {len(ov_errors)} issues:")
            for e in ov_errors:
                print(e)
            overlay_errors.extend(ov_errors)
        else:
            accepted = get_overlay_accepted_alts(overlay)
            deprecated = get_overlay_deprecated(overlay)
            terms = get_overlay_terms(overlay)
            parts = []
            if accepted:
                parts.append(f"{len(accepted)} accepted alt(s)")
            if deprecated:
                parts.append(f"{len(deprecated)} deprecated")
            if terms:
                parts.append(f"{len(terms)} toolkit term(s)")
            print(f"  Valid — {', '.join(parts)}" if parts else "  Valid (empty)")

    if do_dump_overlay:
        # Find toolkit arg
        toolkit_arg = None
        for i, a in enumerate(args):
            if a == "--dump-overlay" and i + 1 < len(args) and not args[i + 1].startswith("-"):
                toolkit_arg = args[i + 1]
                break
        if toolkit_arg and toolkit_arg in overlay_map:
            dump_overlay(overlay_map[toolkit_arg], toolkit_arg)
        elif toolkit_arg:
            print(f"\nNo overlay found for toolkit: {toolkit_arg}")
        else:
            for name, ov in overlay_map.items():
                dump_overlay(ov, name)
        return

    # Check skills
    if do_check:
        toolkit_arg = None
        for i, a in enumerate(args):
            if a == "--check-skills" and i + 1 < len(args) and not args[i + 1].startswith("-"):
                toolkit_arg = args[i + 1]
                break

        if toolkit_arg:
            toolkit_paths = [WORKBENCH / toolkit_arg]
        else:
            toolkit_paths = sorted(p for p in WORKBENCH.iterdir() if p.is_dir())

        for tp in toolkit_paths:
            if not tp.exists():
                print(f"\nERROR: toolkit not found: {tp}")
                continue
            skills_dir = tp / "skills"
            if not skills_dir.exists():
                continue
            print(f"\nSkill name validation: {tp.name}")
            issues = check_skill_names(g, tp)
            if issues:
                print(f"  {len(issues)} issues:")
                for issue in issues:
                    print(issue)
            else:
                print("  All skill names valid")

    # Exit code
    total_errors = len(errors) + len(overlay_errors)
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
