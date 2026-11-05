const STUDIO_FIELD = /^([A-Z][A-Z0-9_]*[ \t]*=[ \t]*)("(?:[^"\\\r\n]|\\[^\r\n])*")[ \t]+#[ \t]*studio:[ \t]*([^\r\n]+)/gm;

export interface DesignField {
  label: string;
  value: string;
  type: "color" | "text";
  start: number;
  end: number;
}

/** Read only the opt-in, top-level string constants authors mark as editable. */
export function designFields(code: string): DesignField[] {
  const fields: DesignField[] = [];
  for (const match of code.matchAll(STUDIO_FIELD)) {
    const [, assignment, literal, description] = match;
    const label = description.trim();
    if (!label) continue;
    try {
      const value = JSON.parse(literal) as string;
      const start = match.index + assignment.length;
      fields.push({ label, value, type: /^#[0-9a-f]{6}$/i.test(value) ? "color" : "text", start, end: start + literal.length });
    } catch {
      // Python accepts escapes outside JSON. Leave those literals to the code editor.
    }
  }
  return fields;
}

export function replaceDesignField(code: string, field: DesignField, value: string) {
  return code.slice(0, field.start) + JSON.stringify(value) + code.slice(field.end);
}
