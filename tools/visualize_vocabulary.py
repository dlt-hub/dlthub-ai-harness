#!/usr/bin/env python3
"""Generate Mermaid diagrams from the dlt SKOS vocabulary.

Usage:
    python tools/visualize_vocabulary.py                              # generate diagrams.md
    python tools/visualize_vocabulary.py --toolkit rest-api-pipeline  # specific overlay only
    python tools/visualize_vocabulary.py --html                       # also emit diagrams.html

Output: .vocabulary/diagrams.md (and optionally .vocabulary/diagrams.html)
"""

import re
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, SKOS

DLT = Namespace("https://dlthub.com/vocab/")

VOCABULARY_PATH = Path(".vocabulary/vocabulary.skos.ttl")
WORKBENCH = Path("workbench")
OVERLAY_GLOB = ".vocabulary/vocabulary.skos.ttl"
OUTPUT_MD = Path(".vocabulary/diagrams.md")
OUTPUT_HTML = Path(".vocabulary/diagrams.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_graph(path: Path) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def get_concepts(g: Graph) -> set[URIRef]:
    return set(g.subjects(RDF.type, SKOS.Concept))


def get_collections(g: Graph) -> set[URIRef]:
    return set(g.subjects(RDF.type, SKOS.Collection))


def concept_id(uri: URIRef) -> str:
    """Extract local name from URI, safe for Mermaid node IDs."""
    local = str(uri).split("/")[-1]
    return local.replace(" ", "_")


def concept_label(g: Graph, uri: URIRef) -> str:
    """Get prefLabel for display."""
    pref = next(g.objects(uri, SKOS.prefLabel), None)
    return str(pref) if pref else concept_id(uri)


def mermaid_safe(label: str) -> str:
    """Escape label for Mermaid node text."""
    return label.replace('"', "#quot;").replace("<", "&lt;").replace(">", "&gt;")


def is_action_concept(uri: URIRef) -> bool:
    return concept_id(uri).startswith("action-")


# ---------------------------------------------------------------------------
# Diagram 1: Entity Taxonomy (broader/narrower hierarchy)
# ---------------------------------------------------------------------------

def generate_taxonomy(g: Graph) -> str:
    lines = ["graph TD"]

    # Style classes
    lines.append("    classDef topConcept fill:#2d6a4f,stroke:#1b4332,color:#fff")
    lines.append("    classDef entity fill:#40916c,stroke:#2d6a4f,color:#fff")
    lines.append("    classDef detail fill:#74c69d,stroke:#40916c,color:#000")
    lines.append("")

    # Collect entity concepts (exclude actions)
    entity_concepts = {c for c in get_concepts(g) if not is_action_concept(c)}

    # Top concepts
    top_concepts: set[URIRef] = set()
    for scheme in g.subjects(RDF.type, SKOS.ConceptScheme):
        for top in g.objects(scheme, SKOS.hasTopConcept):
            top_concepts.add(top)

    # Collect hierarchy edges
    edges: list[tuple[URIRef, URIRef]] = []  # parent -> child
    children_of: dict[URIRef, set[URIRef]] = {}
    for parent in entity_concepts:
        for child in g.objects(parent, SKOS.narrower):
            if child in entity_concepts:
                edges.append((parent, child))
                children_of.setdefault(parent, set()).add(child)

    # Group concepts by collection for subgraphs
    collection_members: dict[str, list[URIRef]] = {}
    for coll in get_collections(g):
        coll_label = str(next(g.objects(coll, SKOS.prefLabel), ""))
        members = [m for m in g.objects(coll, SKOS.member) if m in entity_concepts]
        if members:
            collection_members[coll_label] = members

    # Determine which concepts are in collections
    assigned: set[URIRef] = set()
    for members in collection_members.values():
        assigned.update(members)

    # Emit subgraphs
    for coll_label, members in sorted(collection_members.items()):
        sg_id = "sg_" + re.sub(r"[^a-zA-Z0-9]", "_", coll_label).lower()
        lines.append(f'    subgraph {sg_id}["{mermaid_safe(coll_label)}"]')
        for m in sorted(members, key=lambda u: concept_id(u)):
            cid = concept_id(m)
            clabel = mermaid_safe(concept_label(g, m))
            lines.append(f'        {cid}["{clabel}"]')
        lines.append("    end")
        lines.append("")

    # Concepts not in any collection
    unassigned = entity_concepts - assigned
    for u in sorted(unassigned, key=lambda x: concept_id(x)):
        cid = concept_id(u)
        clabel = mermaid_safe(concept_label(g, u))
        lines.append(f'    {cid}["{clabel}"]')

    # Emit edges
    lines.append("")
    for parent, child in sorted(edges, key=lambda e: (concept_id(e[0]), concept_id(e[1]))):
        lines.append(f"    {concept_id(parent)} --> {concept_id(child)}")

    # Apply styles
    lines.append("")
    for tc in sorted(top_concepts, key=lambda u: concept_id(u)):
        if tc in entity_concepts:
            lines.append(f"    class {concept_id(tc)} topConcept")

    # Leaf nodes get detail style, intermediates get entity style
    all_parents = {p for p, _ in edges}
    all_children = {c for _, c in edges}
    leaves = all_children - all_parents
    intermediates = (entity_concepts - top_concepts - leaves) & all_parents

    for n in sorted(intermediates, key=lambda u: concept_id(u)):
        lines.append(f"    class {concept_id(n)} entity")
    for n in sorted(leaves, key=lambda u: concept_id(u)):
        lines.append(f"    class {concept_id(n)} detail")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diagram 2: Cross-References (skos:related)
# ---------------------------------------------------------------------------

def generate_relationships(g: Graph) -> str:
    lines = ["graph LR"]
    lines.append("    classDef concept fill:#457b9d,stroke:#1d3557,color:#fff")
    lines.append("")

    entity_concepts = {c for c in get_concepts(g) if not is_action_concept(c)}

    # Collect related edges, deduplicate
    seen: set[tuple[str, str]] = set()
    edges: list[tuple[str, str]] = []

    for s in entity_concepts:
        for o in g.objects(s, SKOS.related):
            if o not in entity_concepts:
                continue
            pair = tuple(sorted([concept_id(s), concept_id(o)]))
            if pair not in seen:
                seen.add(pair)
                edges.append(pair)

    # Collect all nodes that participate in related edges
    nodes: set[str] = set()
    for a, b in edges:
        nodes.add(a)
        nodes.add(b)

    # Emit nodes
    for n in sorted(nodes):
        uri = DLT[n]
        clabel = mermaid_safe(concept_label(g, uri))
        lines.append(f'    {n}["{clabel}"]:::concept')

    # Emit edges (dashed)
    lines.append("")
    for a, b in sorted(edges):
        lines.append(f"    {a} -.- {b}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diagram 3: Collections
# ---------------------------------------------------------------------------

def generate_collections(g: Graph) -> str:
    lines = ["graph LR"]
    lines.append("    classDef collection fill:#e76f51,stroke:#9c4127,color:#fff")
    lines.append("    classDef member fill:#f4a261,stroke:#e76f51,color:#000")
    lines.append("")

    for coll in sorted(get_collections(g), key=lambda u: concept_id(u)):
        coll_id = concept_id(coll)
        coll_label = mermaid_safe(str(next(g.objects(coll, SKOS.prefLabel), coll_id)))
        lines.append(f'    {coll_id}["{coll_label}"]:::collection')

    lines.append("")

    # Emit member nodes and edges
    emitted_members: set[str] = set()
    for coll in sorted(get_collections(g), key=lambda u: concept_id(u)):
        coll_id = concept_id(coll)
        for member in sorted(g.objects(coll, SKOS.member), key=lambda u: concept_id(u)):
            m_id = concept_id(member)
            if m_id not in emitted_members:
                m_label = mermaid_safe(concept_label(g, member))
                lines.append(f'    {m_id}["{m_label}"]:::member')
                emitted_members.add(m_id)
            lines.append(f"    {coll_id} --> {m_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diagram 4: Actions Table
# ---------------------------------------------------------------------------

def generate_actions_table(g: Graph) -> str:
    rows: list[tuple[str, str, str]] = []

    for c in sorted(get_concepts(g), key=lambda u: concept_id(u)):
        if not is_action_concept(c):
            continue

        action = str(next(g.objects(c, SKOS.prefLabel), ""))
        defn = str(next(g.objects(c, SKOS.definition), ""))
        note = str(next(g.objects(c, SKOS.scopeNote), ""))

        # Parse valid objects from definition
        m = re.search(r"Valid objects?:\s*([^.]+)", defn)
        objects = m.group(1).strip() if m else "—"

        # Parse deprecated synonyms from scopeNote
        deprecated = "—"
        if note:
            m2 = re.search(r"Deprecated synonyms[^:]*:\s*(.+?)\.?$", note)
            if m2:
                deprecated = m2.group(1).strip()

        # Extract meaning (first sentence before "Valid objects")
        meaning = re.split(r"\s*Valid objects?:", defn)[0].strip().rstrip(".")

        rows.append((action, objects, meaning, deprecated))

    lines = [
        "| Action | Valid Objects | Meaning | Deprecated Synonyms |",
        "|--------|-------------|---------|---------------------|",
    ]
    for action, objects, meaning, deprecated in rows:
        lines.append(f"| **{action}** | {objects} | {meaning} | {deprecated} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diagram 5: Toolkit Overlay
# ---------------------------------------------------------------------------

def generate_overlay(base: Graph, overlay: Graph, toolkit_name: str) -> str:
    lines = ["graph LR"]
    lines.append("    classDef baseRef fill:#adb5bd,stroke:#6c757d,color:#000")
    lines.append("    classDef override fill:#4895ef,stroke:#3f37c9,color:#fff")
    lines.append("    classDef toolkit fill:#7209b7,stroke:#560bad,color:#fff")
    lines.append("    classDef deprecated fill:#e63946,stroke:#a4161a,color:#fff")
    lines.append("")

    overlay_concepts = get_concepts(overlay)
    base_refs: set[str] = set()  # base concept IDs referenced by overlay

    overrides: list[URIRef] = []
    toolkit_terms: list[URIRef] = []
    deprecated: list[URIRef] = []

    for c in sorted(overlay_concepts, key=lambda u: concept_id(u)):
        is_dep = (c, OWL.deprecated, Literal(True)) in overlay
        has_match = list(overlay.objects(c, SKOS.exactMatch))

        if is_dep:
            deprecated.append(c)
        elif has_match:
            overrides.append(c)
        else:
            toolkit_terms.append(c)

    # Emit override concepts
    if overrides:
        lines.append("    %% Overrides (accepted alternatives)")
        for c in overrides:
            cid = "ov_" + concept_id(c)
            pref = mermaid_safe(concept_label(overlay, c))
            alts = [str(a) for a in overlay.objects(c, SKOS.altLabel)]
            alt_text = ", ".join(alts)
            label = f"{pref} (+{alt_text})" if alts else pref
            lines.append(f'    {cid}["{mermaid_safe(label)}"]:::override')

            for match in overlay.objects(c, SKOS.exactMatch):
                base_id = concept_id(match)
                base_refs.add(base_id)
                lines.append(f"    {cid} ==exactMatch==> {base_id}")
        lines.append("")

    # Emit toolkit-specific terms
    if toolkit_terms:
        lines.append("    %% Toolkit-specific terms")
        for c in toolkit_terms:
            cid = "tk_" + concept_id(c)
            clabel = mermaid_safe(concept_label(overlay, c))
            lines.append(f'    {cid}["{clabel}"]:::toolkit')

            # Related to base concepts
            for rel in overlay.objects(c, SKOS.related):
                rel_id = concept_id(rel)
                # Check if target is a base concept or overlay concept
                if rel in get_concepts(base):
                    base_refs.add(rel_id)
                    lines.append(f"    {cid} -.related.- {rel_id}")
                else:
                    # Related to another overlay concept
                    lines.append(f"    {cid} -.related.- tk_{rel_id}")

            # Broader to base concepts
            for br in overlay.objects(c, SKOS.broader):
                br_id = concept_id(br)
                if br in get_concepts(base):
                    base_refs.add(br_id)
                    lines.append(f"    {cid} --broader--> {br_id}")
        lines.append("")

    # Emit deprecated terms
    if deprecated:
        lines.append("    %% Deprecated terms")
        for c in deprecated:
            cid = "dep_" + concept_id(c)
            clabel = mermaid_safe(concept_label(overlay, c))
            lines.append(f'    {cid}["🚫 {clabel}"]:::deprecated')
        lines.append("")

    # Emit base reference nodes (context)
    if base_refs:
        lines.append("    %% Base vocabulary context")
        for br_id in sorted(base_refs):
            uri = DLT[br_id]
            br_label = mermaid_safe(concept_label(base, uri))
            lines.append(f'    {br_id}["{br_label}"]:::baseRef')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble_markdown(
    taxonomy: str,
    relationships: str,
    collections: str,
    actions: str,
    overlays: list[tuple[str, str]],
) -> str:
    sections = [
        "# dlt Vocabulary Diagrams",
        "",
        "> Auto-generated from `.vocabulary/vocabulary.skos.ttl` — do not edit manually.",
        "> Regenerate: `uv run python tools/visualize_vocabulary.py`",
        "",
        "## 1. Entity Taxonomy",
        "",
        "Broader/narrower hierarchy of dlt concepts, grouped by collection.",
        "",
        "```mermaid",
        taxonomy,
        "```",
        "",
        "## 2. Cross-References",
        "",
        "Associative (`skos:related`) links between concepts — no hierarchy.",
        "",
        "```mermaid",
        relationships,
        "```",
        "",
        "## 3. Collections",
        "",
        "Organizational groupings. A concept may belong to multiple collections.",
        "",
        "```mermaid",
        collections,
        "```",
        "",
        "## 4. Workspace Actions",
        "",
        "Canonical action-object pairs for skill naming.",
        "",
        actions,
        "",
    ]

    for name, overlay_mermaid in overlays:
        sections.extend([
            f"## 5. Toolkit Overlay: {name}",
            "",
            f"How **{name}** extends the base vocabulary.",
            "",
            "Legend: "
            "🔵 override (promotes hiddenLabel → altLabel) · "
            "🟣 toolkit term · "
            "🔴 deprecated · "
            "⚪ base concept (context)",
            "",
            "```mermaid",
            overlay_mermaid,
            "```",
            "",
        ])

    return "\n".join(sections)


def assemble_html(md_content: str) -> str:
    """Wrap markdown with Mermaid blocks in a self-contained HTML page."""
    # Extract mermaid blocks and replace with div tags
    html_body = md_content

    # Convert markdown headers
    for level in range(3, 0, -1):
        prefix = "#" * level
        html_body = re.sub(
            rf"^{prefix} (.+)$",
            rf"<h{level}>\1</h{level}>",
            html_body,
            flags=re.MULTILINE,
        )

    # Convert mermaid code blocks to <pre class="mermaid">
    html_body = re.sub(
        r"```mermaid\n(.*?)```",
        r'<pre class="mermaid">\n\1</pre>',
        html_body,
        flags=re.DOTALL,
    )

    # Convert markdown tables to HTML tables
    table_lines: list[str] = []
    in_table = False
    out_lines: list[str] = []

    for line in html_body.split("\n"):
        if line.startswith("|"):
            table_lines.append(line)
            in_table = True
        else:
            if in_table:
                out_lines.append(_md_table_to_html(table_lines))
                table_lines = []
                in_table = False
            out_lines.append(line)
    if table_lines:
        out_lines.append(_md_table_to_html(table_lines))

    html_body = "\n".join(out_lines)

    # Convert blockquotes
    html_body = re.sub(r"^> (.+)$", r"<blockquote>\1</blockquote>", html_body, flags=re.MULTILINE)

    # Convert bold
    html_body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_body)

    # Wrap paragraphs (simple: lines not already in tags)
    html_body = re.sub(r"^([^<\n].+)$", r"<p>\1</p>", html_body, flags=re.MULTILINE)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>dlt Vocabulary Diagrams</title>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
               max-width: 1200px; margin: 0 auto; padding: 2rem; color: #24292f; }}
        h1 {{ border-bottom: 1px solid #d0d7de; padding-bottom: 0.3em; }}
        h2 {{ border-bottom: 1px solid #d0d7de; padding-bottom: 0.3em; margin-top: 2em; }}
        blockquote {{ color: #656d76; border-left: 3px solid #d0d7de; padding-left: 1em; margin: 1em 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
        th, td {{ border: 1px solid #d0d7de; padding: 6px 13px; text-align: left; }}
        th {{ background: #f6f8fa; font-weight: 600; }}
        pre.mermaid {{ background: #f6f8fa; padding: 1em; border-radius: 6px; text-align: center; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""


def _md_table_to_html(lines: list[str]) -> str:
    """Convert markdown table lines to HTML table."""
    if len(lines) < 2:
        return "\n".join(lines)

    rows: list[list[str]] = []
    for i, line in enumerate(lines):
        if i == 1 and re.match(r"^\|[\s\-:|]+\|$", line):
            continue  # skip separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)

    html = ["<table>"]
    for i, row in enumerate(rows):
        tag = "th" if i == 0 else "td"
        html.append("  <tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in row) + "</tr>")
    html.append("</table>")
    return "\n".join(html)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    do_html = "--html" in args
    toolkit_filter = None
    for i, a in enumerate(args):
        if a == "--toolkit" and i + 1 < len(args):
            toolkit_filter = args[i + 1]

    if not VOCABULARY_PATH.exists():
        print(f"ERROR: vocabulary not found at {VOCABULARY_PATH}")
        sys.exit(1)

    # Load base vocabulary
    print(f"Loading {VOCABULARY_PATH}...")
    g = load_graph(VOCABULARY_PATH)
    concepts = get_concepts(g)
    print(f"  {len(g)} triples, {len(concepts)} concepts")

    # Generate diagrams
    print("Generating diagrams...")

    print("  1. Entity taxonomy")
    taxonomy = generate_taxonomy(g)

    print("  2. Cross-references")
    relationships = generate_relationships(g)

    print("  3. Collections")
    collections = generate_collections(g)

    print("  4. Actions table")
    actions = generate_actions_table(g)

    # Discover and generate overlay diagrams
    overlays: list[tuple[str, str]] = []
    for toolkit_dir in sorted(WORKBENCH.iterdir()):
        if not toolkit_dir.is_dir():
            continue
        if toolkit_filter and toolkit_dir.name != toolkit_filter:
            continue
        overlay_path = toolkit_dir / OVERLAY_GLOB
        if not overlay_path.exists():
            continue

        print(f"  5. Overlay: {toolkit_dir.name}")
        overlay = load_graph(overlay_path)
        overlay_mermaid = generate_overlay(g, overlay, toolkit_dir.name)
        overlays.append((toolkit_dir.name, overlay_mermaid))

    # Assemble and write
    md = assemble_markdown(taxonomy, relationships, collections, actions, overlays)
    OUTPUT_MD.write_text(md)
    print(f"\nWrote {OUTPUT_MD}")

    if do_html:
        html = assemble_html(md)
        OUTPUT_HTML.write_text(html)
        print(f"Wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
