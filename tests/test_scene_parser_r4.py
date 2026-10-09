"""Round 4: an if/elif/else or match/case inside a loop runs one branch per pass,
so the timeline counts only the branch with the most animation runs (estimated)."""

import textwrap

from scene_parser import get_scene_animations


def _steps(body: str):
    code = "from manim import *\nclass S(Scene):\n    def construct(self):\n" + textwrap.indent(
        textwrap.dedent(body), " " * 8
    )
    return get_scene_animations(code)["S"]


def _summary(steps):
    return [(s["label"], bool(s.get("estimated")), bool(s.get("alternative"))) for s in steps]


def _counted_runs(steps):
    return sum(s.get("repeat", 1) for s in steps if not s.get("alternative"))


def test_if_else_in_a_loop_counts_the_bigger_branch():
    steps = _steps(
        """
        for i in range(3):
            if i % 2:
                self.play(A())
            else:
                self.play(B())
                self.play(C())
        """
    )
    assert _summary(steps) == [("A()", True, True), ("B()", True, False), ("C()", True, False)]
    assert _counted_runs(steps) == 6  # 2 per pass x 3, not 3 per pass


def test_tie_takes_the_first_branch():
    steps = _steps(
        """
        for i in range(2):
            if i:
                self.play(A())
            else:
                self.play(B())
        """
    )
    assert _summary(steps) == [("A()", True, False), ("B()", True, True)]
    assert _counted_runs(steps) == 2


def test_if_without_else_counts_the_body_as_estimated():
    steps = _steps(
        """
        for i in range(4):
            if i:
                self.play(A())
            self.wait()
        """
    )
    assert _summary(steps) == [("A()", True, False), ("Wait 1s", False, False)]
    assert _counted_runs(steps) == 8


def test_elif_chain_and_nested_branches_take_the_max_recursively():
    steps = _steps(
        """
        for i in range(2):
            if i == 0:
                self.play(A())
            elif i == 1:
                if x:
                    self.play(B())
                    self.play(C())
                    self.play(D())
                else:
                    self.play(E())
            else:
                self.play(F())
                self.play(G())
        """
    )
    assert _summary(steps) == [
        ("A()", True, True),
        ("B()", True, False),
        ("C()", True, False),
        ("D()", True, False),
        ("E()", True, True),
        ("F()", True, True),
        ("G()", True, True),
    ]


def test_inner_loops_weigh_the_branch():
    steps = _steps(
        """
        for i in range(2):
            if i:
                self.play(A())
                self.play(B())
            else:
                for _ in range(5):
                    self.play(C())
        """
    )
    assert _summary(steps) == [("A()", True, True), ("B()", True, True), ("C()", True, False)]
    assert _counted_runs(steps) == 10


def test_match_case_in_a_loop():
    steps = _steps(
        """
        for k in range(3):
            match k:
                case 0:
                    self.play(A())
                case 1 if flag:
                    self.play(B())
                    self.play(C())
                case _:
                    pass
        """
    )
    assert _summary(steps) == [("A()", True, True), ("B()", True, False), ("C()", True, False)]


def test_match_without_a_wildcard_may_run_nothing():
    steps = _steps(
        """
        for k in range(3):
            match k:
                case 0:
                    self.play(A())
        """
    )
    assert _summary(steps) == [("A()", True, False)]


def test_while_loops_follow_the_same_rule():
    steps = _steps(
        """
        while running:
            if x:
                self.play(A())
            else:
                self.play(B())
                self.wait(2)
        """
    )
    assert _summary(steps) == [("A()", True, True), ("B()", True, False), ("Wait 2s", True, False)]


def test_conditions_and_guards_are_still_scanned():
    steps = _steps(
        """
        for k in range(2):
            if self.play(A()):
                self.play(B())
        """
    )
    assert _summary(steps) == [("A()", True, False), ("B()", True, False)]
    assert "alternative" not in steps[0]
    # The test runs every pass, so it is not part of a branch.
    assert steps[0]["estimated"] is True  # duration guessed from defaults


def test_branches_outside_loops_are_unchanged():
    steps = _steps(
        """
        if x:
            self.play(A())
        else:
            self.play(B())
        """
    )
    assert [s.get("alternative") for s in steps] == [None, None]
    assert "repeat" not in steps[0]


def test_steps_stay_in_source_order_with_loop_chains():
    steps = _steps(
        """
        for i in range(2):
            self.play(A())
            if i:
                self.play(B())
            else:
                self.play(C())
            self.play(D())
        """
    )
    assert [s["line"] for s in steps] == sorted(s["line"] for s in steps)
    assert all(s["loops"] == [[5, 8, 2]] for s in steps)
