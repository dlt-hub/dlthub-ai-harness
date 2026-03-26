#!/usr/bin/env python3
"""Terminology linter for dlt documentation.

Two-phase approach:
  1. NLP pre-filter (spaCy + sentence-transformers): finds candidate violations
     cheaply and locally using embedding similarity.
  2. LLM review (optional): sends candidates to Claude for final verdict on
     context-dependent cases (enumerations, definitions, general English usage).

Usage:
    # Candidates only (NLP pass):
    python tools/glossary_lint.py workbench/
    python tools/glossary_lint.py --severity error workbench/

    # Full pipeline — NLP + LLM review:
    python tools/glossary_lint.py --review workbench/
    python tools/glossary_lint.py --review --cli workbench/         # via Claude CLI
    python tools/glossary_lint.py --review --model opus workbench/  # pick model

    # Inspect the prompt that would be sent to the LLM:
    python tools/glossary_lint.py --review --prompt workbench/

    # JSON output (candidates or verdicts):
    python tools/glossary_lint.py --json workbench/
    python tools/glossary_lint.py --review --json workbench/

Exit code 0 if clean, 1 if candidates/violations found.
"""

import argparse
import json as json_mod
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import spacy
import yaml
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

GLOSSARY_PATH = Path("terminology/glossary.yaml")
PROMPT_TEMPLATE_PATH = Path("terminology/prompt_template.txt")

# Similarity threshold: how close must the context be to the glossary definition
# for us to consider the term might be used in the domain-specific sense.
DOMAIN_SIMILARITY_THRESHOLD = 0.30

# Patterns to strip before analysis
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")
FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
URL_RE = re.compile(r"https?://\S+")
MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]+\)")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GlossaryRule:
    """A single deprecated -> preferred term rule with its definition embedding."""

    preferred: str
    deprecated: str
    definition: str
    severity: str
    note: str
    definition_embedding: np.ndarray | None = field(default=None, repr=False)


@dataclass
class Candidate:
    """A potential terminology violation found by the NLP pass."""

    file: str
    line: int
    column: int
    found: str
    preferred: str
    severity: str
    definition: str
    note: str
    context: str
    similarity: float

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "found": self.found,
            "preferred": self.preferred,
            "severity": self.severity,
            "definition": self.definition,
            "note": self.note,
            "context": self.context,
            "similarity": round(self.similarity, 3),
        }


# ---------------------------------------------------------------------------
# Glossary loading
# ---------------------------------------------------------------------------


def load_glossary(path: Path = GLOSSARY_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_rules(terms: list[dict], min_severity: str) -> list[GlossaryRule]:
    """Build lint rules from glossary terms."""
    severity_order = {"error": 0, "warning": 1, "suggestion": 2}
    min_level = severity_order.get(min_severity, 2)

    rules = []
    for term in terms:
        severity = term.get("severity", "suggestion")
        if severity_order.get(severity, 2) > min_level:
            continue

        preferred = term["preferred"]
        definition = term.get("definition", "").strip()
        note = term.get("note", "").strip()

        for dep in term.get("deprecated", []):
            rules.append(
                GlossaryRule(
                    preferred=preferred,
                    deprecated=dep,
                    definition=definition,
                    severity=severity,
                    note=note,
                )
            )

    return rules


def precompute_embeddings(rules: list[GlossaryRule], model: SentenceTransformer) -> None:
    """Precompute embeddings combining deprecated term, preferred term, and definition.

    Embedding the terms alongside the definition produces higher similarity
    scores for sentences that use the deprecated term in a domain-relevant
    context, compared to embedding the definition alone.
    """
    texts = [f"{r.deprecated}. {r.preferred}. {r.definition}" for r in rules]
    if not texts:
        return
    embeddings = model.encode(texts, show_progress_bar=False)
    for rule, emb in zip(rules, embeddings):
        rule.definition_embedding = emb


# ---------------------------------------------------------------------------
# Markdown cleanup
# ---------------------------------------------------------------------------


def strip_markdown(text: str) -> tuple[str, dict[int, int]]:
    """Strip markdown formatting, preserving line count for mapping."""
    text = FRONTMATTER_RE.sub(lambda m: "\n" * m.group().count("\n"), text)
    text = CODE_BLOCK_RE.sub(lambda m: "\n" * m.group().count("\n"), text)
    text = INLINE_CODE_RE.sub(lambda m: " " * len(m.group()), text)
    text = URL_RE.sub(lambda m: " " * len(m.group()), text)
    text = MD_LINK_RE.sub(lambda m: m.group(1), text)

    cleaned = []
    for ln in text.split("\n"):
        ln = re.sub(r"^#+\s+", "", ln)
        ln = re.sub(r"^\s*(?:\d+\.\s+|[a-z]\)\s+|[-*+]\s+)", "", ln)
        ln = re.sub(r"[*_|>~#\\]", " ", ln)
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        cleaned.append(ln)

    line_map = {i + 1: i + 1 for i in range(len(cleaned))}
    return "\n".join(cleaned), line_map


# ---------------------------------------------------------------------------
# NLP candidate extraction
# ---------------------------------------------------------------------------


def extract_sentences(text: str, nlp: spacy.language.Language) -> list[dict]:
    """Extract sentences from cleaned text with line/column positions."""
    sentences = []
    for line_num, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        doc = nlp(stripped)
        for sent in doc.sents:
            sent_text = sent.text.strip()
            if len(sent_text) < 5:
                continue
            col = line.find(sent_text) + 1 if sent_text in line else 1
            sentences.append({"text": sent_text, "line": line_num, "column": col})
    return sentences


def check_sentence(
    sentence: dict,
    rules: list[GlossaryRule],
    embedder: SentenceTransformer,
    threshold: float,
) -> list[Candidate]:
    """Find candidate violations in a sentence using embedding similarity."""
    candidates = []
    sent_text = sentence["text"]
    sent_lower = sent_text.lower()

    for rule in rules:
        dep_lower = rule.deprecated.lower()
        if dep_lower not in sent_lower:
            continue

        pattern = re.compile(r"\b" + re.escape(dep_lower) + r"\b", re.IGNORECASE)
        matches = list(pattern.finditer(sent_text))
        if not matches:
            continue

        sent_embedding = embedder.encode([sent_text], show_progress_bar=False)[0]
        similarity = float(cosine_similarity([sent_embedding], [rule.definition_embedding])[0][0])
        if similarity < threshold:
            continue

        for match in matches:
            candidates.append(
                Candidate(
                    file="",
                    line=sentence["line"],
                    column=sentence["column"] + match.start(),
                    found=match.group(),
                    preferred=rule.preferred,
                    severity=rule.severity,
                    definition=rule.definition,
                    note=rule.note,
                    context=sent_text,
                    similarity=similarity,
                )
            )

    return candidates


def scan_file(
    filepath: Path,
    rules: list[GlossaryRule],
    embedder: SentenceTransformer,
    nlp: spacy.language.Language,
    threshold: float,
) -> list[Candidate]:
    """Extract candidates from a single markdown file."""
    text = filepath.read_text(encoding="utf-8")
    cleaned, line_map = strip_markdown(text)

    candidates = []
    for sentence in extract_sentences(cleaned, nlp):
        for c in check_sentence(sentence, rules, embedder, threshold):
            c.file = str(filepath)
            c.line = line_map.get(c.line, c.line)
            candidates.append(c)

    return candidates


def collect_markdown_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".md" else []
    return sorted(path.rglob("*.md"))


def extract_candidates(
    paths: list[Path],
    glossary: dict,
    severity: str,
    threshold: float,
) -> list[Candidate]:
    """Run the full NLP candidate extraction pass."""
    print("Loading models...", file=sys.stderr)
    nlp = spacy.load("en_core_web_md")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")

    rules = build_rules(glossary.get("terms", []), severity)
    precompute_embeddings(rules, embedder)
    print(f"Loaded {len(rules)} rules from glossary.", file=sys.stderr)

    all_candidates: list[Candidate] = []
    files_checked = 0

    for path in paths:
        for md_file in collect_markdown_files(path):
            files_checked += 1
            print(f"  Scanning {md_file}...", file=sys.stderr)
            all_candidates.extend(scan_file(md_file, rules, embedder, nlp, threshold))

    print(
        f"{len(all_candidates)} candidate(s) in {files_checked} file(s).",
        file=sys.stderr,
    )
    return all_candidates


# ---------------------------------------------------------------------------
# LLM review — prompt assembly
# ---------------------------------------------------------------------------


def extract_relevant_terms(candidates: list[Candidate], glossary: dict) -> list[dict]:
    """Extract only the glossary terms referenced by the candidates."""
    preferred_terms = {c.preferred for c in candidates}
    found_terms = {c.found.lower() for c in candidates}

    relevant = []
    for term in glossary.get("terms", []):
        if term["preferred"] in preferred_terms:
            relevant.append(term)
            continue
        for dep in term.get("deprecated", []):
            if dep.lower() in found_terms:
                relevant.append(term)
                break

    return relevant


def format_term_rules(terms: list[dict]) -> str:
    """Format glossary terms into a compact block for the prompt."""
    lines = []
    for term in terms:
        preferred = term["preferred"]
        deprecated = term.get("deprecated", [])
        definition = term.get("definition", "").strip()
        note = term.get("note", "").strip()

        lines.append(f"### `{preferred}`")
        if definition:
            lines.append(f"**Definition:** {definition}")
        if deprecated:
            dep_str = ", ".join(f'"{d}"' for d in deprecated)
            lines.append(f"**Deprecated alternatives:** {dep_str}")
        if note:
            lines.append(f"**Note:** {note}")

        for v in term.get("variants", []):
            lines.append(f'  - "{v["term"]}": {v.get("definition", "")}')

        lines.append("")

    return "\n".join(lines)


def format_candidates_for_prompt(candidates: list[Candidate]) -> str:
    """Format candidates into a numbered list for the prompt."""
    lines = []
    for i, c in enumerate(candidates):
        lines.append(f"**Candidate {i}** [{c.severity.upper()}]")
        lines.append(f"  File: {c.file}:{c.line}")
        lines.append(f'  Found: "{c.found}"')
        lines.append(f'  Preferred: "{c.preferred}"')
        lines.append(f'  Context: "{c.context}"')
        lines.append(f"  Similarity: {c.similarity:.3f}")
        lines.append("")
    return "\n".join(lines)


def build_prompt(candidates: list[Candidate], glossary: dict) -> str:
    """Assemble the full prompt from template + relevant terms + candidates."""
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    relevant_terms = extract_relevant_terms(candidates, glossary)
    prompt = template.replace("{{TERM_RULES}}", format_term_rules(relevant_terms))
    prompt = prompt.replace("{{CANDIDATES}}", format_candidates_for_prompt(candidates))
    return prompt


# ---------------------------------------------------------------------------
# LLM review — invocation
# ---------------------------------------------------------------------------


def call_llm_api(prompt: str, model: str) -> str:
    """Call the Anthropic API directly."""
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it with: export ANTHROPIC_API_KEY=your-key\n"
            "Or use --cli to use the Claude Code CLI instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def call_llm_cli(prompt: str, model: str) -> str:
    """Call Claude via the Claude Code CLI."""
    import shutil
    import subprocess

    claude_bin = shutil.which("claude")
    if not claude_bin:
        print(
            "ERROR: 'claude' CLI not found on PATH.\n"
            "Install it from https://claude.ai/claude-code\n"
            "Or remove --cli to use the Anthropic API instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    result = subprocess.run(
        [claude_bin, "-p", "--model", model],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"ERROR: claude CLI failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    return result.stdout


def parse_verdicts(response_text: str) -> list[dict]:
    """Parse the LLM JSON response into verdicts."""
    text = response_text.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()
    return json_mod.loads(text)


def review_candidates(
    candidates: list[Candidate],
    glossary: dict,
    *,
    use_cli: bool,
    model: str | None,
    output_prompt: bool,
) -> list[dict]:
    """Send candidates to the LLM and return parsed verdicts."""
    prompt = build_prompt(candidates, glossary)

    if output_prompt:
        print(prompt)
        sys.exit(0)

    if use_cli:
        resolved_model = model or "sonnet"
        print(
            f"Reviewing {len(candidates)} candidates with Claude CLI ({resolved_model})...",
            file=sys.stderr,
        )
        response_text = call_llm_cli(prompt, resolved_model)
    else:
        resolved_model = model or "claude-sonnet-4-20250514"
        print(
            f"Reviewing {len(candidates)} candidates with API ({resolved_model})...",
            file=sys.stderr,
        )
        response_text = call_llm_api(prompt, resolved_model)

    return parse_verdicts(response_text)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


GITHUB_SEVERITY_MAP = {"error": "error", "warning": "warning", "suggestion": "notice"}


def github_annotation(
    file: str, line: int, col: int, severity: str, title: str, message: str
) -> str:
    """Format a GitHub Actions workflow annotation command."""
    gh_level = GITHUB_SEVERITY_MAP.get(severity, "notice")
    return f"::{gh_level} file={file},line={line},col={col},title={title}::{message}"


def print_candidates(candidates: list[Candidate], *, github: bool = False) -> None:
    """Print candidates grouped by file."""
    by_file: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_file.setdefault(c.file, []).append(c)

    for filepath, file_candidates in sorted(by_file.items()):
        if not github:
            print(f"\n{filepath}:")
        for c in file_candidates:
            if github:
                print(
                    github_annotation(
                        file=c.file,
                        line=c.line,
                        col=c.column,
                        severity=c.severity,
                        title="Terminology",
                        message=f"Use '{c.preferred}' instead of '{c.found}'",
                    )
                )
            else:
                sev = c.severity.upper()
                print(
                    f"  :{c.line}:{c.column}: [{sev}] "
                    f"'{c.found}' -> '{c.preferred}' "
                    f"(similarity: {c.similarity:.2f})"
                )
                print(f'    "{c.context}"')


def print_verdicts(
    verdicts: list[dict], candidates: list[Candidate], *, github: bool = False
) -> None:
    """Print LLM verdicts in human-readable or GitHub annotation format."""
    violations = [v for v in verdicts if v["verdict"] == "VIOLATION"]
    acceptable = [v for v in verdicts if v["verdict"] == "ACCEPTABLE"]

    if github:
        for v in violations:
            c = candidates[v["id"]]
            message = f"Use '{c.preferred}' instead of '{c.found}'. {v['reason']}"
            if v.get("suggestion"):
                message += f" Suggestion: {v['suggestion']}"
            print(
                github_annotation(
                    file=c.file,
                    line=c.line,
                    col=c.column,
                    severity=c.severity,
                    title="Terminology",
                    message=message,
                )
            )
    else:
        if violations:
            print(f"\nVIOLATIONS ({len(violations)}):\n")
            for v in violations:
                c = candidates[v["id"]]
                print(f"  {c.file}:{c.line}")
                print(f'    Found: "{c.found}" -> "{c.preferred}"')
                print(f'    Context: "{c.context}"')
                print(f"    Reason: {v['reason']}")
                if v.get("suggestion"):
                    print(f'    Suggestion: "{v["suggestion"]}"')
                print()

        if acceptable:
            print(f"ACCEPTABLE ({len(acceptable)}):\n")
            for v in acceptable:
                c = candidates[v["id"]]
                print(f"  {c.file}:{c.line}")
                print(f'    "{c.found}" kept — {v["reason"]}')
            print()

        print(f"Summary: {len(violations)} violation(s), {len(acceptable)} acceptable")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Terminology linter for dlt documentation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories to scan")
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "suggestion"],
        default="suggestion",
        help="Minimum severity to report (default: suggestion)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DOMAIN_SIMILARITY_THRESHOLD,
        help=f"Similarity threshold (default: {DOMAIN_SIMILARITY_THRESHOLD})",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--github",
        action="store_true",
        help="Output GitHub Actions annotations (::warning, ::error, ::notice)",
    )

    review_group = parser.add_argument_group("LLM review")
    review_group.add_argument(
        "--review",
        action="store_true",
        help="Send candidates to LLM for final verdict",
    )
    review_group.add_argument(
        "--cli",
        action="store_true",
        help="Use Claude Code CLI instead of Anthropic API",
    )
    review_group.add_argument(
        "--model",
        default=None,
        help="Model (API: claude-sonnet-4-20250514; CLI: sonnet, opus, haiku)",
    )
    review_group.add_argument(
        "--prompt",
        action="store_true",
        help="Print the assembled LLM prompt and exit",
    )

    args = parser.parse_args()

    if not GLOSSARY_PATH.exists():
        print(f"ERROR: Glossary not found at {GLOSSARY_PATH}", file=sys.stderr)
        sys.exit(1)

    glossary = load_glossary()

    # Phase 1: NLP candidate extraction
    candidates = extract_candidates(args.paths, glossary, args.severity, args.threshold)

    if not candidates:
        print("Clean: no candidates found.")
        sys.exit(0)

    # Phase 2: LLM review (optional)
    if args.review or args.prompt:
        if not PROMPT_TEMPLATE_PATH.exists():
            print(
                f"ERROR: Prompt template not found at {PROMPT_TEMPLATE_PATH}",
                file=sys.stderr,
            )
            sys.exit(1)

        verdicts = review_candidates(
            candidates,
            glossary,
            use_cli=args.cli,
            model=args.model,
            output_prompt=args.prompt,
        )

        if args.json:
            print(json_mod.dumps(verdicts, indent=2))
        else:
            print_verdicts(verdicts, candidates, github=args.github)

        has_violations = any(v["verdict"] == "VIOLATION" for v in verdicts)
        sys.exit(1 if has_violations else 0)

    # No review — output candidates
    if args.json:
        print(json_mod.dumps([c.to_dict() for c in candidates], indent=2))
    else:
        print_candidates(candidates, github=args.github)
        if not args.github:
            print(f"\n{len(candidates)} candidate(s) found.")

    sys.exit(1)


if __name__ == "__main__":
    main()
