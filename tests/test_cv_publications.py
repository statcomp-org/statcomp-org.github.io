"""Checks for bibliography inclusion, trainee matching, and LaTeX generation."""

import copy
import importlib.util
import json
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
