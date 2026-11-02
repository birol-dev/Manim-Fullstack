import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";

import { fieldErrorsOf, friendlyFieldMessage, hasErrorsUnder, matchErrors } from "./errors";
import { fieldPaths, fieldsOf } from "./schemaForm";
import { CHART_SCHEMA } from "./test/fixtures";

describe("field errors from responses", () => {
  it("reads the studio's {detail, errors} body", () => {
    const error = new ApiError("Invalid input for chart.", 422, {
      detail: "Invalid input for chart.",
      errors: [
        { field: "params.bars.2.value", message: "Input should be a valid number" },
        { field: "settings.length", message: "Input should be less than or equal to 60" },
      ],
    });
    expect(fieldErrorsOf(error)).toEqual([
      { field: "params.bars.2.value", message: "Input should be a valid number" },
      { field: "settings.length", message: "Input should be less than or equal to 60" },
    ]);
  });

  it("reads FastAPI's own validation body", () => {
    const error = new ApiError("Request failed", 422, {
      detail: [{ loc: ["body", "settings", "aspect"], msg: "Input should be '16:9' or '9:16'", type: "literal_error" }],
    });
    expect(fieldErrorsOf(error)).toEqual([{ field: "settings.aspect", message: "Input should be '16:9' or '9:16'" }]);
  });

  it("ignores other errors", () => {
    expect(fieldErrorsOf(new ApiError("Boom", 500, { detail: "Boom" }))).toEqual([]);
    expect(fieldErrorsOf(new Error("offline"))).toEqual([]);
    expect(fieldErrorsOf(null)).toEqual([]);
  });
});

describe("matching errors to fields", () => {
  const fields = fieldsOf(CHART_SCHEMA);
  const values = { bars: [{}, {}, {}], points: [{}] };
  const known = [...fieldPaths(fields, values), "settings.length", "settings.background", "settings.background.color"];

  it("puts each error on its field, row cell or nearest parent", () => {
    const { byPath, unmatched } = matchErrors(
      [
        { field: "params.bars.2.value", message: "Input should be a valid number" },
        { field: "params.logo.str", message: "Input should be a valid string" },
        { field: "params.points", message: "List should have at least 1 item after validation, not 0" },
        { field: "settings.background.color", message: "Value error, Use a color like #2563EB." },
        { field: "params.bars.7.label", message: "String should have at most 24 characters" },
        { field: "params.nope", message: "Extra inputs are not permitted" },
        { field: "settings.brand.font", message: "Too long" },
      ],
      known,
    );
    expect(byPath["params.bars.2.value"]).toEqual(["Type a number."]);
    expect(byPath["params.logo"]).toEqual(["Input should be a valid string"]);
    expect(byPath["params.points"]).toEqual(["Add at least 1."]);
    expect(byPath["settings.background.color"]).toEqual(["Use a color like #2563EB."]);
    // Row 7 isn't on screen: the table as a whole shows it.
    expect(byPath["params.bars"]).toEqual(["Use at most 24 characters."]);
    expect(unmatched.map((error) => error.field)).toEqual(["params.nope", "settings.brand.font"]);
    expect(hasErrorsUnder(byPath, "params.bars")).toBe(true);
    expect(hasErrorsUnder(byPath, "params.bar")).toBe(false);
    expect(hasErrorsUnder(byPath, "settings")).toBe(true);
  });

  it("rewrites validator messages in plain words", () => {
    expect(friendlyFieldMessage("String should have at least 1 character")).toBe("This can't be empty.");
    expect(friendlyFieldMessage("Input should be greater than or equal to 3")).toBe("Use 3 or more.");
    expect(friendlyFieldMessage("Input should be a valid integer, got a number with a fractional part")).toBe("Type a whole number.");
    expect(friendlyFieldMessage("Input should be 'ring', 'bar' or 'big'")).toBe("Pick one of the options.");
    expect(friendlyFieldMessage("Field required")).toBe("This is needed.");
    expect(friendlyFieldMessage("something odd")).toBe("Something odd");
  });
});
