import unittest

from tests import CLI_LIB  # noqa: F401
from spec_driven import meta, router


def m(tier="M", mode="feature", scope=None, **status):
    d = meta.new("demo-change", mode, "b", "c")
    d["complexity"] = tier
    if scope is not None:
        d["bugfixScope"] = scope
    for p, s in status.items():
        d["phaseStatus"][p.replace("_", ".").lstrip("p")] = s
    return d


class SkipTest(unittest.TestCase):
    def test_feature_table(self):
        for phase in ("2", "3", "5", "7"):
            self.assertIsNotNone(router.skip_reason(phase, m("S")), phase)
            self.assertIsNone(router.skip_reason(phase, m("M")), phase)
            self.assertIsNone(router.skip_reason(phase, m("L")), phase)
        for phase in ("1", "4", "6", "8", "8.5", "8.9", "9"):
            self.assertIsNone(router.skip_reason(phase, m("S")), phase)

    def test_bugfix_rules(self):
        small = {"files": 1, "crossService": False, "ddl": False, "publicApi": False}
        self.assertIsNotNone(router.skip_reason("2", m(mode="bugfix", scope=small)))
        self.assertIsNotNone(router.skip_reason("3", m(mode="bugfix", scope=small)))
        for key, value in (("files", 3), ("crossService", True), ("ddl", True), ("publicApi", True)):
            self.assertIsNone(router.skip_reason("2", m(mode="bugfix", scope=dict(small, **{key: value}))), key)
        self.assertIsNotNone(router.skip_reason("3", m(mode="bugfix", scope=dict(small, files=5))))
        self.assertIsNone(router.skip_reason("3", m(mode="bugfix", scope=dict(small, ddl=True))))
        self.assertIsNone(router.skip_reason("3", m(mode="bugfix", scope=dict(small, publicApi=True))))

    def test_bugfix_without_assessment_runs(self):
        self.assertIsNone(router.skip_reason("2", m(mode="bugfix")))
        self.assertIsNotNone(router.skip_reason("2", m("S", mode="bugfix")))


class NextTest(unittest.TestCase):
    def test_first_open_phase(self):
        d = m(p0="passed", p1="passed", p2="skipped")
        self.assertEqual(router.next_phase(d, {}), "3")

    def test_retried_phase_before_stale_ones(self):
        d = m(p0="passed", p1="in_progress", p2="stale", p3="stale", p4="pending")
        self.assertEqual(router.next_phase(d, {}), "1")
        d["phaseStatus"]["1"] = "passed"
        self.assertEqual(router.next_phase(d, {}), "2")

    def test_done(self):
        d = m()
        d["phaseStatus"] = {p: "passed" for p in meta.PHASES}
        self.assertIsNone(router.next_phase(d, {}))
        self.assertIn("归档", router.summary(d, {})["action"])

    def test_review_rounds(self):
        self.assertEqual([router.review_rounds(m(t)) for t in "SML"], [0, 1, 2])

    def test_gates_of(self):
        self.assertEqual(router.gates_of("6"), ["6", "6.5", "6.7"])
        self.assertEqual(router.gates_of("3"), ["3"])


if __name__ == "__main__":
    unittest.main()
