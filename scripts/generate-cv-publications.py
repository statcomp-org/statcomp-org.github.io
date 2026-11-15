#!/usr/bin/env python3
"""Generate the CV publication fragment using Pandoc and the standard library."""

import argparse
import collections
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = [
    ("books", "Books and Edited Volumes"),
    ("chapters", "Book Chapters and Conference Proceedings"),
    ("articles", "Refereed Journal Articles"),
    ("magazine", "Magazine Articles and Other Contributions"),
    ("review", "Book Reviews"),
    ("software", "Software Packages"),
    ("under-review", "Manuscripts Under Review"),
]


def pandoc(source, source_format, target, *options):
    return subprocess.run(
        ["quarto", "pandoc", "--from", source_format, "--to", target, *options],
        input=source, text=True, capture_output=True, check=True,
    ).stdout


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text).lower()
                   if c.isalnum() and not unicodedata.combining(c))


def name_parts(person):
    given = re.findall(r"[^\W\d_]+", person.get("given", ""), re.UNICODE)
    return normalize(person.get("family", "")), [normalize(x) for x in given]


def matches(person, candidate):
    family, given = name_parts(person)
    other_family, other_given = name_parts(candidate)
    if family != other_family or not given or not other_given:
        return False
    # Initials may abbreviate a name; full given names must agree. The roster
    # often omits middle names, so compare only the supplied shared components.
    return all(a == b or (min(len(a), len(b)) == 1 and a[0] == b[0])
               for a, b in zip(given, other_given))


def read_trainees(cv, config):
    section = re.search(r"\\section\{Students\}(.*?)(?=\\section\{|\\end\{vita\})", cv, re.S)
    if not section:
        raise ValueError("Cannot find the Students section in jyanCV.tex")
    students = []
    for line in section[1].splitlines():
        if line.lstrip().startswith(r"\item "):
            name = re.split(r",?\s*Ph\.D\.|:\s*Ph\.D\.|\s+\(\d{4}",
                            line.strip()[6:], maxsplit=1)[0].rstrip(" ,:")
            details = line.strip()[6 + len(name):].lstrip(" ,:")
            degree = re.match(r"Ph\.D\.\s*,?\s*(expected\s+)?(\d{4})", details, re.I)
            if details.startswith("Ph.D.") and not degree:
                raise ValueError(f"Cannot read PhD graduation year for {name}")
            graduation_year = int(degree[2]) if degree and not degree[1] else None
            students.append((name, graduation_year))
    buffers = config.get("post_phd_buffer_years", {})
    unknown = (set(config["aliases"]) | set(buffers)) - {name for name, _ in students}
    if unknown:
        raise ValueError(f"Trainee settings refer to names absent from the CV: {unknown}")
    roster = []
    for name, graduation_year in students:
        buffer = buffers.get(name)
        if name in buffers and (type(buffer) is not int or buffer < 0 or graduation_year is None):
            raise ValueError(f"A trainee cutoff needs a completed PhD and a nonnegative buffer: {name}")
        trainee_through = graduation_year + buffer if buffer is not None else None
        variants = [re.sub(r"\([^)]*\)", "", name).strip()]
        variants += config["aliases"].get(name, [])
        people = []
        for variant in variants:
            given, family = variant.rsplit(" ", 1)
            people.append({"family": family, "given": given,
                           "graduation_year": graduation_year,
                           "trainee_through": trainee_through})
        roster.append((name, people))
    for person in config["additional_trainees"]:
        roster.append((person["given"] + " " + person["family"], [person]))
    return roster


def read_bibliography(paths):
    entries, years = [], {}
    for path in paths:
        source = path.read_text()
        # Pandoc handles all BibTeX parsing. Retain only the raw year field
        # separately because it discards the project's nonstandard 2026+ dates.
        chunks = re.split(r"(?m)^@\w+\s*\{", source)[1:]
        keys = []
        for chunk in chunks:
            key = chunk.split(",", 1)[0].strip()
            keys.append(key)
            year = re.search(r'(?im)(?:^|[,\n])\s*year\s*=\s*[{"]?(\d{4}\+?)', chunk)
            if year:
                years[key] = year[1]
        duplicates = [key for key, n in collections.Counter(keys).items() if n > 1]
        if duplicates:
            raise ValueError(f"Duplicate bibliography keys in {path.name}: {duplicates}")
        entries.extend(json.loads(pandoc(source, "bibtex", "csljson")))
    ids = [x["id"] for x in entries]
    duplicates = [key for key, n in collections.Counter(ids).items() if n > 1]
    if duplicates:
        raise ValueError(f"Duplicate bibliography keys across files: {duplicates}")
    for entry in entries:
        key = entry["id"]
        if key not in years:
            raise ValueError(f"Missing four-digit year for {key}")
        entry["cv-year"] = years[key]
        if years[key].endswith("+"):
            entry["issued"] = {"date-parts": [[int(years[key].rstrip("+"))]]}
        categories = re.findall(r"\bcv:([\w-]+)", entry.get("keyword", ""))
        if len(categories) > 1:
            raise ValueError(f"Multiple CV categories for {key}")
        category = categories[0] if categories else {
            "book": "books", "chapter": "chapters", "paper-conference": "chapters",
            "article-journal": "articles",
        }.get(entry["type"])
        if category not in dict(SECTIONS) or category == "software":
            raise ValueError(f"Set a supported cv: category in keywords for {key}")
        entry["cv-category"] = category
    return entries


def read_software(source):
    references = dict(re.findall(r"(?m)^\[([^]]+)\]:\s*(\S+)", source))
    languages = list(re.finditer(r"(?m)^## ([^\n]+?) packages(?: on [^\n]+)?\s*$", source))
    headings = list(re.finditer(
        r"(?m)^### \{([^}]+)\}: (.*?) \{#([^}]+)\}\s*$", source))
    entries, seen, author_records = [], set(), []
    for i, heading in enumerate(headings):
        name, description, anchor = heading.groups()
        if name in seen:
            raise ValueError(f"Duplicate software section: {name}")
        seen.add(name)
        end = headings[i + 1].start() if i + 1 < len(headings) else len(source)
        body = source[heading.end():end]
        authors = re.search(r"<!-- cv-authors: (.*?) -->", body)
        if not authors:
            raise ValueError(f"Missing cv-authors metadata for {name}")
        author_records.append("@misc{software-" + name + ", author={" + authors[1] + "}}")
        link = re.search(r"<!-- cv-url: (\S+) -->", body)
        url = link[1] if link else references.get(name + "-cran")
        if not url:
            raise ValueError(f"Missing software link for {name}")
        language = next((m[1] for m in reversed(languages) if m.start() < heading.start()), None)
        if not language:
            raise ValueError(f"Put {name} under a language heading such as '## R packages'")
        address = urlparse(url)
        host = address.hostname or ""
        if host in {"cran.r-project.org", "cran.rstudio.com", "cloud.r-project.org"}:
            distribution = "CRAN archive" if "/archive/" in address.path.lower() else "CRAN"
        else:
            distribution = {"github.com": "GitHub", "gitlab.com": "GitLab",
                            "pypi.org": "PyPI"}.get(host, host)
        entries.append({"id": "software-" + name, "type": "software",
                        "title": description, "URL": url, "cv-package": name,
                        "cv-language": language, "cv-distribution": distribution,
                        "cv-category": "software", "cv-year": ""})
    if not entries:
        raise ValueError("No software sections found")
    people = {x["id"]: x["author"] for x in json.loads(pandoc(
        "\n".join(author_records), "bibtex", "csljson"))}
    for entry in entries:
        entry["author"] = people[entry["id"]]
    return entries


def annotate(entries, roster, overrides):
    used = set()
    for entry in entries:
        for index, author in enumerate(entry.get("author", []), 1):
            identity = author.get("family", "") + ", " + author.get("given", "")
            candidates = {name: variants[0].get("trainee_through")
                          for name, variants in roster
                          if any(matches(author, variant) for variant in variants)}
            override = overrides.get(entry["id"], {}).get(str(index))
            if override:
                used.add((entry["id"], str(index)))
                if override["author"] != identity:
                    raise ValueError(f"Stale trainee override: {entry['id']} author {index}")
                trainee = override["trainee"]
            else:
                if len(candidates) > 1:
                    raise ValueError(f"Ambiguous trainee: {entry['id']}: {identity}: {candidates}")
                trainee = bool(candidates)
                if trainee:
                    trainee_through = next(iter(candidates.values()))
                    year = entry.get("cv-year", "").rstrip("+")
                    if trainee_through is not None and year:
                        trainee = int(year) <= trainee_through
            if trainee:
                author["family"] = "CVTRAINEEMARK" + author["family"]
    expected = {(key, i) for key, positions in overrides.items() for i in positions}
    if expected != used:
        raise ValueError(f"Unused trainee overrides: {expected - used}")


def sort_key(entry):
    authors = entry.get("author", entry.get("editor", []))
    author_key = " ".join(x.get("family", "") + x.get("given", "") for x in authors)
    author_key = normalize(author_key.replace("CVTRAINEEMARK", ""))
    year = entry["cv-year"]
    if entry["cv-category"] == "software":
        return (0, 0, entry["cv-package"].lower(), "", entry["id"])
    return (-int(year.endswith("+")), -int(year.rstrip("+")), author_key,
            normalize(entry["title"]), entry["id"])


def render(entries):
    citation_entries = copy.deepcopy(entries)
    for entry in citation_entries:
        if entry["cv-category"] == "software":
            entry.pop("URL", None)
        for author in entry.get("author", []):
            author["given"] = re.sub(r"\b([A-Z][a-z]{2,})\.(?=\s|$)", r"\1", author.get("given", ""))
    doc = json.loads(pandoc(json.dumps(citation_entries), "csljson", "json"))
    cited = json.loads(pandoc(json.dumps(doc), "json", "json", "--citeproc",
                             "--csl=" + str(ROOT / "cv-publications.csl")))
    blocks = {}

    def collect(node):
        if isinstance(node, dict):
            if node.get("t") == "Div" and node["c"][0][0].startswith("ref-"):
                blocks[node["c"][0][0][4:]] = node["c"][1]
            else:
                for value in node.values():
                    collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(cited["blocks"])
    if set(blocks) != {x["id"] for x in entries}:
        raise ValueError("Citeproc did not return every bibliography entry")
    output = []

    def raw(text):
        output.append({"t": "RawBlock", "c": ["latex", text]})

    raw("% Generated by make cv-publications. Edit the sources, not this file.")
    for category, title in SECTIONS:
        members = sorted((x for x in entries if x["cv-category"] == category), key=sort_key)
        if not members:
            continue
        raw("\\subsection{" + title + "}\n\\begin{enumerate}")
        for entry in members:
            raw("% " + entry["id"] + "\n\\item")
            content = copy.deepcopy(blocks[entry["id"]])
            if entry["cv-year"].endswith("+"):
                # Citeproc requires a numeric date. Restore the plus sign only
                # in this entry's rendered date, never in titles or page ranges.
                def restore_year(node):
                    if isinstance(node, dict):
                        if node.get("t") == "Str":
                            node["c"] = node["c"].replace(
                                "(" + entry["cv-year"][:-1] + ")",
                                "(" + entry["cv-year"] + ")")
                        else:
                            for value in node.values():
                                restore_year(value)
                    elif isinstance(node, list):
                        for value in node:
                            restore_year(value)
                restore_year(content)
            if category == "software":
                label = f"({entry['cv-language']}; {entry['cv-distribution']})."
                label_inlines = []
                for word in label.split():
                    label_inlines.extend([{"t": "Space"}, {"t": "Str", "c": word}])
                content[0]["c"][0:0] = [
                    {"t": "Link", "c": [["", [], []], [
                        {"t": "Code", "c": [["", [], []], entry["cv-package"]]}
                    ], [entry["URL"], ""]]},
                    *label_inlines,
                    {"t": "Space"},
                ]
            output.extend(content)
        raw("\\end{enumerate}")
    fragment = {"pandoc-api-version": doc["pandoc-api-version"], "meta": {}, "blocks": output}
    latex = pandoc(json.dumps(fragment), "json", "latex", "--wrap=auto", "--ascii")
    return latex.replace("CVTRAINEEMARK", "*").replace("\\item\n\n", "\\item ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the local generated fragment is missing or stale")
    args = parser.parse_args()
    config = json.loads((ROOT / "cv-trainees.json").read_text())
    roster = read_trainees((ROOT / "jyanCV.tex").read_text(), config)
    entries = read_bibliography([ROOT / "jyan.bib", ROOT / "jyan-cv-extra.bib"])
    entries += read_software((ROOT / "software.qmd").read_text())
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("A bibliography key conflicts with a software identifier")
    annotate(entries, roster, config["author_overrides"])
    result = render(entries)
    destination = ROOT / "cv-publications.tex"
    if args.check:
        if not destination.exists() or destination.read_text() != result:
            sys.exit("cv-publications.tex is stale; run make cv-publications")
    else:
        destination.write_text(result)
    counts = collections.Counter(x["cv-category"] for x in entries)
    print("CV publications: " + ", ".join(f"{category}={counts[category]}" for category, _ in SECTIONS))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error) + ("\n" + error.stderr if isinstance(error, subprocess.CalledProcessError) else ""))
