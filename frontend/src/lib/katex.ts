const MAX_LENGTH = 180;

function clip(text: string): string {
  return text.length > MAX_LENGTH ? `${text.slice(0, MAX_LENGTH)}…` : text;
}

function describeToken(token: string): string {
  const bare = token.replace(/^['"]|['"]$/g, "");
  if (bare === "EOF" || bare === "end of input") return "the end of the formula";
  return `'${bare}'`;
}

/**
 * Turn a KaTeX ParseError message into a short, readable hint.
 *
 * KaTeX messages look like
 * `KaTeX parse error: Unexpected end of input in a macro argument, expected '}' at end of input: \frac{a`
 * — the trailing `at position N: …` / `at end of input: …` part repeats the
 * formula with combining underlines, so it is dropped.
 */
export function friendlyKatex(message: string): string {
  let cleaned = message.replace(/^KaTeX parse error:\s*/i, "").trim();
  // Position suffix: " at position 7: \frac{a̲}" or " at end of input: \frac{a".
  cleaned = cleaned.replace(/\s+at (?:position \d+|end of input)\s*:[\s\S]*$/i, "").trim();

  const MISSING_BRACE = "Missing closing brace '}': a { … } group isn't closed.";
  const expected = cleaned.match(/Expected ('[^']*'|"[^"]*"), got ('[^']*'|"[^"]*")/i);
  if (expected) {
    const want = expected[1].slice(1, -1);
    const got = expected[2].slice(1, -1);
    if (want === "}" && got === "EOF") return MISSING_BRACE;
    if (want === "EOF" && got === "}") return "There's an extra closing brace '}' without a matching '{'.";
    if (want === "\\right") return "\\left needs a matching \\right (use \\right. for an invisible one).";
    return clip(`Check the formula: expected ${describeToken(expected[1])}, but found ${describeToken(expected[2])}.`);
  }
  if (/Unexpected end of input/i.test(cleaned)) {
    const want = cleaned.match(/expected ('[^']*'|"[^"]*")/i);
    if (want && want[1].slice(1, -1) === "}") return MISSING_BRACE;
    return clip(`The formula ends too early${want ? `: expected ${describeToken(want[1])}` : ""}. Check for a missing brace or argument.`);
  }
  const undefinedCommand = cleaned.match(/Undefined control sequence:?\s*(\\[A-Za-z@]+|\\.)?/i);
  if (undefinedCommand) {
    return clip(
      undefinedCommand[1]
        ? `Unknown command ${undefinedCommand[1]}. Check the spelling, or that the package providing it is loaded.`
        : "Unknown command. Check the spelling of each \\command.",
    );
  }
  const groupAfter = cleaned.match(/Expected group (?:after|as argument to) ['"]?([^'"\s]+)['"]?/i);
  if (groupAfter) {
    const command = groupAfter[1];
    return clip(`${command} needs an argument in braces, e.g. ${command}{x}.`);
  }
  if (/Extra \}|Unexpected ['"]?\}['"]?/i.test(cleaned)) {
    return "There's an extra closing brace '}' without a matching '{'.";
  }
  if (/Missing \}/i.test(cleaned)) return MISSING_BRACE;
  if (/Double (?:superscript|subscript)/i.test(cleaned)) {
    const kind = /superscript/i.test(cleaned) ? "superscripts (^)" : "subscripts (_)";
    return clip(`Two ${kind} in a row. Group them with braces, e.g. x^{ab} or {x^a}^b.`);
  }
  if (/function '\$'|character: '\$'|Missing \$/i.test(cleaned)) {
    return "Remove the $ signs: the formula is already in math mode.";
  }
  const environment = cleaned.match(/(?:No such|Unknown) environment:?\s*['"]?([^'"\s]+)/i);
  if (environment) return clip(`Unknown environment '${environment[1]}'. Check the name in \\begin{…}.`);
  if (/^Mismatch/i.test(cleaned)) {
    const pair = cleaned.match(/(\\begin\{[^}]*\}) matched by (\\end\{[^}]*\})/);
    return clip(pair ? `${pair[1]} is closed by ${pair[2]}; the names must match.` : "\\begin{…} and \\end{…} don't match.");
  }
  return clip(cleaned || "This formula couldn't be read. Check for a missing brace or symbol.");
}
