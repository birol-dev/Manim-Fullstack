// Shared filename rule vectors, also checked by tests/test_filename_rules_r3.py against
// backend/workspace_paths.py. See /workspace/manim-audit-compare/r3/FILENAME-RULE.md.
import { describe, expect, it } from "vitest";
import rules from "../../../tests/fixtures/filename_rules.json";
import { foldFilename, toScriptName, validateScriptName } from "./format";

interface Vector { input: string; script_name: string; error: string | null; ui_script_name?: string }

const vectors = rules.vectors as Vector[];

describe("shared filename rule (tests/fixtures/filename_rules.json)", () => {
  it.each(vectors.map((vec) => [JSON.stringify(vec.input).slice(0, 40), vec] as const))(
    "%s",
    (_label, vec) => {
      const name = toScriptName(vec.input);
      expect(name).toBe(vec.ui_script_name ?? vec.script_name);
      expect(validateScriptName(vec.script_name)).toBe(vec.error);
    },
  );

  it.each(rules.direct_names.map((vec) => [vec.name, vec.error] as const))("validates %s directly", (name, error) => {
    expect(validateScriptName(name)).toBe(error);
  });

  it.each(rules.collisions.map((vec) => [vec.a, vec.b, vec.collide] as const))("%s vs %s collide=%s", (a, b, collide) => {
    expect(foldFilename(a) === foldFilename(b)).toBe(collide);
    const problem = validateScriptName(a, [b]);
    if (collide && a !== b) expect(problem).toContain("differ only by case");
    if (!collide) expect(problem).toBeNull();
  });

  it("covers the round 3 cases", () => {
    const inputs = vectors.map((vec) => vec.input);
    for (const needed of ["Foo.PY", "x.py.", "x .py", "COM¹.py", "ＣＯＭ１.py", "cafe\u0301.py"]) {
      expect(inputs).toContain(needed);
    }
  });

  it("Foo.PY becomes Foo.py, not Foo.PY.py", () => {
    expect(toScriptName("Foo.PY")).toBe("Foo.py");
    expect(toScriptName(" Foo.PY ")).toBe("Foo.py");
    expect(toScriptName("x.py.")).toBe("x.py.");
    expect(validateScriptName(toScriptName("x.py."))).toBe("Filename cannot start or end with a dot or space.");
  });

  it("is idempotent", () => {
    for (const vec of vectors) {
      const once = toScriptName(vec.input);
      expect(toScriptName(once)).toBe(once);
    }
  });
});
