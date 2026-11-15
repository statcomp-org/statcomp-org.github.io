"""Checks for bibliography inclusion, trainee matching, and LaTeX generation."""

import copy
import importlib.util
import json
import re
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "cv", Path(__file__).resolve().parents[1] / "scripts/generate-cv-publications.py")
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)


class CVPublicationsTests(unittest.TestCase):
    def test_student_section_includes_both_subsections_and_stops_at_next_section(self):
        source = r'''
\section{Positions}
\item Unrelated Person (2026): Not a trainee.
\section{Students}
\subsection{Ph.D. Thesis Advisees}
\begin{enumerate}
\item Jane Doe, Ph.D. 2025: Thesis.
\end{enumerate}
\subsection{Undergraduate Thesis Advisees}
\begin{enumerate}
\item John Smith (2024): Thesis.
\end{enumerate}
\section{Teaching Accomplishments}
\item Another Person (2026): Award.
'''
        roster = cv.read_trainees(source, {"aliases": {}, "additional_trainees": []})
        self.assertEqual([name for name, _ in roster], ["Jane Doe", "John Smith"])
        self.assertEqual([people[0]["graduation_year"] for _, people in roster],
                         [2025, None])

    def test_phd_buffer_handles_aliases_and_forthcoming(self):
        source = r'''
\section{Students}
\item Greg Vaughan, Ph.D. 2020: Thesis.
\section{Teaching Accomplishments}
'''
        roster = cv.read_trainees(source, {
            "aliases": {"Greg Vaughan": ["Gregory Vaughan"]},
            "additional_trainees": [],
            "post_phd_buffer_years": {"Greg Vaughan": 2},
        })
        for year, expected in [("2019", True), ("2022", True), ("2023", False),
                               ("2022+", True), ("2023+", False), ("", True)]:
            with self.subTest(year=year):
                entry = {"id": "example", "cv-year": year,
                         "author": [{"family": "Vaughan", "given": "Gregory"}]}
                cv.annotate([entry], roster, {})
                self.assertEqual(entry["author"][0]["family"].startswith("CVTRAINEEMARK"),
                                 expected)

    def test_current_phds_and_undergraduates_do_not_expire(self):
        source = r'''
\section{Students}
\item Jane Doe, Ph.D., expected 2020: Thesis.
\item John Smith (2020): Undergraduate thesis.
\section{Teaching Accomplishments}
'''
        roster = cv.read_trainees(source, {"aliases": {}, "additional_trainees": []})
        entry = {"id": "example", "cv-year": "2026", "author": [
            {"family": "Doe", "given": "Jane"},
            {"family": "Smith", "given": "John"},
        ]}
        cv.annotate([entry], roster, {})
        self.assertTrue(all(a["family"].startswith("CVTRAINEEMARK") for a in entry["author"]))

    def test_phd_coauthors_are_evaluated_independently(self):
        source = r'''
\section{Students}
\item Jane Doe: Ph.D. 2020: Thesis.
\item John Smith, Ph.D. 2024: Thesis.
\section{Teaching Accomplishments}
'''
        roster = cv.read_trainees(source, {"aliases": {}, "additional_trainees": [],
                                         "post_phd_buffer_years": {"Jane Doe": 2, "John Smith": 2}})
        entry = {"id": "example", "cv-year": "2026", "author": [
            {"family": "Doe", "given": "Jane"},
            {"family": "Smith", "given": "John"},
        ]}
        cv.annotate([entry], roster, {})
        self.assertEqual([a["family"].startswith("CVTRAINEEMARK")
                          for a in entry["author"]], [False, True])

    def test_two_year_policy_is_limited_to_the_three_named_alumni(self):
        config = json.loads((cv.ROOT / "cv-trainees.json").read_text())
        roster = cv.read_trainees((cv.ROOT / "jyanCV.tex").read_text(), config)
        for family, given, last_year in [("Prates", "Marcos", 2013),
                                        ("Chiou", "Steven", 2015),
                                        ("Lautier", "Jackson", 2025)]:
            for year in [last_year, last_year + 1]:
                with self.subTest(author=family, year=year):
                    entry = {"id": "example", "cv-year": str(year), "author": [
                        {"family": family, "given": given},
                    ]}
                    cv.annotate([entry], roster, {})
                    self.assertEqual(entry["author"][0]["family"].startswith("CVTRAINEEMARK"),
                                     year == last_year)
        entry = {"id": "example", "cv-year": "2026", "author": [
            {"family": "Wang", "given": "Wenjie"},
            {"family": "Ma", "given": "Sai"},
            {"family": "Wu", "given": "Jing"},
            {"family": "Xiao", "given": "Shiying"},
        ]}
        cv.annotate([entry], roster, {})
        self.assertTrue(all(a["family"].startswith("CVTRAINEEMARK") for a in entry["author"]))

    def test_full_given_names_do_not_match_on_initial_alone(self):
        self.assertFalse(cv.matches({"family": "Wang", "given": "Tianying"},
                                    {"family": "Wang", "given": "Tiandong"}))
        self.assertTrue(cv.matches({"family": "Wang", "given": "T."},
                                   {"family": "Wang", "given": "Tiandong"}))

    def test_roster_aliases_and_former_trainees(self):
        config = json.loads((cv.ROOT / "cv-trainees.json").read_text())
        roster = cv.read_trainees((cv.ROOT / "jyanCV.tex").read_text(), config)
        entries = [{"id": "example", "author": [
            {"family": "Chiou", "given": "Steven"},
            {"family": "Vaughan", "given": "Gregory"},
            {"family": "Godoy", "given": "Lucas da C."},
            {"family": "Yan", "given": "Jun"},
        ]}]
        cv.annotate(entries, roster, {})
        self.assertEqual([a["family"].startswith("CVTRAINEEMARK")
                          for a in entries[0]["author"]], [True, True, True, False])

    def test_ambiguous_names_require_override_and_overrides_guard_author_order(self):
        roster = [("one", [{"family": "Wang", "given": "Tao"}]),
                  ("two", [{"family": "Wang", "given": "Tiandong"}])]
        entry = {"id": "ambiguous", "author": [{"family": "Wang", "given": "T."}]}
        with self.assertRaisesRegex(ValueError, "Ambiguous trainee"):
            cv.annotate([copy.deepcopy(entry)], roster, {})
        override = {"ambiguous": {"1": {"author": "Wang, T.", "trainee": True}}}
        cv.annotate([copy.deepcopy(entry)], roster, override)
        override["ambiguous"]["1"]["author"] = "Wang, Tiandong"
        with self.assertRaisesRegex(ValueError, "Stale trainee override"):
            cv.annotate([copy.deepcopy(entry)], roster, override)

    def test_excluded_wangs_are_not_annotated(self):
        config = json.loads((cv.ROOT / "cv-trainees.json").read_text())
        roster = cv.read_trainees((cv.ROOT / "jyanCV.tex").read_text(), config)
        entries = [{"id": "example", "author": [
            {"family": "Wang", "given": "Tao"},
            {"family": "Wang", "given": "Feng"},
            {"family": "Wang", "given": "Tiandong"},
        ]}]
        cv.annotate(entries, roster, {})
        self.assertEqual([a["family"].startswith("CVTRAINEEMARK")
                          for a in entries[0]["author"]], [False, False, True])

    def test_duplicate_keys_across_bibliographies_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ["main.bib", "extra.bib"]]
            for path in paths:
                path.write_text('@article{same, author={Yan, Jun}, title={Title}, year={2026}}')
            with self.assertRaisesRegex(ValueError, "Duplicate bibliography keys across"):
                cv.read_bibliography(paths)

    def test_missing_software_authors_fail(self):
        with self.assertRaisesRegex(ValueError, "Missing cv-authors"):
            cv.read_software('### {package}: A Package {#package}\n\nDescription.\n')

    def test_software_languages_and_distributions(self):
        source = '''
## R packages
### {example}: An R Package {#example}
<!-- cv-authors: Yan, Jun -->
[example-cran]: https://CRAN.R-project.org/package=example
### {archived}: An Archived Package {#archived}
<!-- cv-authors: Yan, Jun -->
<!-- cv-url: https://cran.r-project.org/src/contrib/Archive/archived/ -->
### {spice}: Sparse Precision Estimation {#spice}
<!-- cv-authors: Yan, Jun -->
<!-- cv-url: https://github.com/Carol-seven/spice -->
## Python packages
### {python-example}: A Python Package {#python-example}
<!-- cv-authors: Yan, Jun -->
<!-- cv-url: https://pypi.org/project/python-example/ -->
### {python-repo}: A Python Repository {#python-repo}
<!-- cv-authors: Yan, Jun -->
<!-- cv-url: https://github.com/example/python-repo -->
'''
        entries = cv.read_software(source)
        self.assertEqual([(e["cv-language"], e["cv-distribution"]) for e in entries],
                         [("R", "CRAN"), ("R", "CRAN archive"),
                          ("R", "GitHub"), ("Python", "PyPI"), ("Python", "GitHub")])
        output = cv.render(entries)
        self.assertIn(r"\subsection{Software Packages}", output)
        for label in ["(R; CRAN).", "(R; CRAN archive).", "(R; GitHub).",
                      "(Python; PyPI).", "(Python; GitHub)."]:
            self.assertIn(label, " ".join(output.split()))

    def test_software_language_heading_is_required(self):
        source = '''### {example}: Example {#example}
<!-- cv-authors: Yan, Jun -->
<!-- cv-url: https://github.com/example/example -->
'''
        with self.assertRaisesRegex(ValueError, "language heading"):
            cv.read_software(source)

    def test_software_catalog_uses_current_spice_name(self):
        source = (cv.ROOT / "software.qmd").read_text()
        entries = cv.read_software(source)
        names = {e["cv-package"] for e in entries}
        self.assertIn("spice", names)
        self.assertNotIn("fcstat", names)
        table = source.split('<div id="r-pkg-details">')[0]
        table_names = re.findall(r"(?m)^\|\s*\[([^]]+)\]\(#", table)
        r_names = {e["cv-package"] for e in entries if e["cv-language"] == "R"}
        self.assertEqual(set(table_names), r_names)
        self.assertEqual(len(table_names), len(r_names))
        self.assertEqual(table_names, sorted(table_names, key=str.lower))

    def test_publication_title_links_prefer_doi_and_fall_back_to_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "links.bib"
            path.write_text(r'''
@article{doi,
  author={Yan, Jun}, year={2026}, title={A {Formatted} Title},
  doi={10.1234/example}, url={https://example.org/unused}}
@book{url,
  author={Yan, Jun}, year={2025}, title={A Book Title},
  url={https://example.org/book}}
@article{plain,
  author={Yan, Jun}, year={2024}, title={An Unlinked Title}}
''')
            entries = cv.read_bibliography([path])
            original = copy.deepcopy(entries)
            output = " ".join(cv.render(entries).split())
            self.assertIn(r"\href{https://doi.org/10.1234/example}{A Formatted title}",
                          output)
            self.assertIn(r"\emph{\href{https://example.org/book}{A book title}}",
                          output)
            self.assertNotIn("https://example.org/unused", output)
            self.assertIn("An unlinked title", output)
            self.assertEqual(output.count(r"\href{"), 2)
            self.assertEqual(output.count("10.1234/example"), 1)
            self.assertEqual(entries, original)

    def test_forthcoming_year_categories_order_and_latex_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bib"
            path.write_text(r'''
@article{future,
  author={Doe, Jane and Yan, Jun}, year={2026+},
  title={Research with 50\% and {A\&B}}, journal={Research Journal},
  note={Forthcoming}}
@article{magazine,
  author={Yan, Jun}, year={2025}, title={Magazine article},
  journal={Chance}, keywords={cv:magazine}}
@unpublished{reviewing,
  author={Yan, Jun}, year={2026}, title={Submitted manuscript},
  keywords={cv:under-review}}
''')
            entries = cv.read_bibliography([path])
            self.assertEqual([e["cv-category"] for e in entries],
                             ["articles", "magazine", "under-review"])
            output = cv.render(entries)
            self.assertIn("(2026+)", output)
            self.assertIn(r"50\%", output)
            self.assertIn(r"A\&B", output)
            self.assertIn("Forthcoming", output)
            self.assertLess(output.index("% future"), output.index("% magazine"))
            self.assertLess(output.index("% magazine"), output.index("% reviewing"))


if __name__ == "__main__":
    unittest.main()
