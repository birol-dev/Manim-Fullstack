import { useId } from "react";
import { parameterGroup, parameterKeys, parameterLabel, parameterOptions, parameterRange, type ShaderDefinition, type ShaderParams, type ShaderValue } from "./catalog";

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const id = useId();
  const alpha = value.length === 9 ? parseInt(value.slice(7), 16) : 255;
  return <div className="shader-color-field">
    <label htmlFor={id}>{label}</label>
    <div className="shader-color-value">
      <input id={id} type="color" aria-label={`${label} color`} value={value.slice(0, 7)} onChange={(event) => onChange(event.target.value + (alpha < 255 ? alpha.toString(16).padStart(2, "0") : ""))} />
      <input key={value} className="shader-hex" aria-label={`${label} hex`} defaultValue={value.toUpperCase()} maxLength={9} onBlur={(event) => {
        if (/^#[\da-f]{6}([\da-f]{2})?$/i.test(event.target.value)) onChange(event.target.value);
        else event.target.value = value.toUpperCase();
      }} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} />
      <input className="shader-opacity" type="number" aria-label={`${label} opacity`} title="Opacity (%)" min={0} max={100} value={Math.round(alpha / 255 * 100)} onChange={(event) => {
        const opacity = Math.round(Math.max(0, Math.min(100, Number(event.target.value))) / 100 * 255);
        onChange(value.slice(0, 7) + (opacity < 255 ? opacity.toString(16).padStart(2, "0") : ""));
      }} /><span className="shader-percent">%</span>
    </div>
  </div>;
}

function Field({ shader, name, value, onChange }: { shader: ShaderDefinition; name: string; value: ShaderValue; onChange: (value: ShaderValue) => void }) {
  const id = useId();
  const label = name === "size" && ["dithering", "image-dithering"].includes(shader.id) ? "Dither size"
    : name === "noise" && ["spiral", "swirl"].includes(shader.id) ? "Noise power" : parameterLabel(name);
  if (Array.isArray(value)) return <div className="shader-palette">{value.map((color, index) => <ColorField key={index} label={`Color ${index + 1}`} value={color} onChange={(next) => onChange(value.map((item, i) => i === index ? next : item))} />)}</div>;
  if (typeof value === "string" && name.startsWith("color")) return <ColorField label={label} value={value} onChange={onChange} />;
  if (typeof value === "boolean") return <label className="shader-toggle" htmlFor={id}><span>{label}</span><input id={id} type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} /></label>;
  if (typeof value === "string") return <label className="shader-select-field" htmlFor={id}><span>{label}</span><select id={id} aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>{parameterOptions(shader, name).map((option) => <option key={option} value={option}>{option.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase())}</option>)}</select></label>;
  const range = parameterRange(shader, name);
  const multiplier = range.unit === "%" ? 100 : 1;
  const displayed = Math.round(value * multiplier * 100) / 100;
  const min = Math.min(range.min, value), max = Math.max(range.max, value);
  return <div className="shader-slider-field">
    <div><label htmlFor={id}>{label}</label><span><input type="number" aria-label={`${label} value`} min={min * multiplier} max={max * multiplier} step={range.step * multiplier} value={displayed} onChange={(event) => {
      if (event.target.value === "") return;
      const next = Number(event.target.value) / multiplier;
      if (Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next)));
    }} />{range.unit}</span></div>
    <input id={id} type="range" min={min} max={max} step={range.step} value={value} aria-valuetext={`${displayed}${range.unit}`} onChange={(event) => onChange(Number(event.target.value))} />
  </div>;
}

export function ShaderControls({ shader, params, onChange }: { shader: ShaderDefinition; params: ShaderParams; onChange: (key: string, value: ShaderValue) => void }) {
  const groups = new Map<string, string[]>();
  for (const key of parameterKeys(shader)) {
    const group = parameterGroup(key, shader);
    groups.set(group, [...(groups.get(group) ?? []), key]);
  }
  return <div className="shader-control-groups">{Array.from(groups, ([group, keys]) => {
    const optional = group === "Crumples" ? "crumples" : group === "Distortion" ? "distortion" : null;
    const fields = <div className="shader-group-fields">{keys.map((name) => <Field key={name} shader={shader} name={name} value={params[name]} onChange={(value) => onChange(name, value)} />)}</div>;
    if (group === "Parameters") return <section key={group} aria-label="Parameters">{fields}</section>;
    if (optional) return <section key={group} className="shader-optional-group"><label className="shader-group-enable"><span>{group}</span><input type="checkbox" aria-label={`Enable ${group.toLowerCase()}`} checked={Number(params[optional]) > 0} onChange={(event) => onChange(optional, event.target.checked ? optional === "crumples" ? 0.4 : 0.5 : 0)} /></label>{Number(params[optional]) > 0 && fields}</section>;
    return <details key={group} open={group === "Colors"}><summary>{group}</summary>{fields}</details>;
  })}</div>;
}
