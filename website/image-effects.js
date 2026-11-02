// The same source photograph is passed into each real Paper image shader.
export const natureSource = 'assets/nature-river.webp';
export const imageEffects = {
  glass: { name: 'Fluted Glass', file: 'fluted-glass', shader: 'flutedGlassFragmentShader' },
  water: { name: 'Water', file: 'water', shader: 'waterFragmentShader' },
  paper: { name: 'Paper Texture', file: 'paper-texture', shader: 'paperTextureFragmentShader' },
};

export function imageUniforms(engine, image, effect, strength = 0.65, scale = 1) {
  const color = engine.getShaderColorFromString;
  const base = { u_image: image, u_fit: 2, u_scale: scale, u_rotation: 0, u_offsetX: 0, u_offsetY: 0,
    u_originX: 0.5, u_originY: 0.5, u_worldWidth: 0, u_worldHeight: 0 };
  if (effect === 'glass') return { ...base, u_colorBack: color('#15352d'), u_colorShadow: color('#112c27'),
    u_colorHighlight: color('#ffffff'), u_shadows: strength * 0.14, u_highlights: strength * 0.12,
    u_size: 0.65, u_angle: 0, u_shape: 1, u_distortionShape: 1, u_distortion: strength,
    u_shift: 0, u_stretch: 0, u_blur: 0, u_edges: 0.1, u_marginLeft: 0, u_marginRight: 0,
    u_marginTop: 0, u_marginBottom: 0, u_grainMixer: 0, u_grainOverlay: strength * 0.025 };
  if (effect === 'water') return { ...base, u_colorBack: color('#15352d'), u_colorHighlight: color('#d9fff4'),
    u_highlights: strength * 0.08, u_layering: strength * 0.25, u_waves: strength * 0.55,
    u_edges: strength * 0.4, u_caustic: strength * 0.2, u_size: 0.9 };
  return { ...base, u_isImage: true, u_colorBack: color('#ece5d4'), u_colorPaper: color('#fff5dc'),
    u_colorShadow: color('#8c846b'), u_blending: 1, u_distortion: strength * 0.5, u_clip: false,
    u_angle: 300, u_seed: 4, u_roughness: strength * 0.4, u_roughnessSize: 0.5, u_roughnessRows: 0,
    u_fiber: strength * 0.45, u_fiberSize: 0.5, u_folds: strength * 0.6, u_foldSizeX: 1,
    u_foldSizeY: 1, u_foldOffsetX: 0, u_foldOffsetY: 0, u_wrinkles: strength * 0.7,
    u_wrinkleSize: 0.65, u_crumples: 0, u_crumpleCount: 6, u_drops: 0,
    u_noiseTexture: engine.getShaderNoiseTexture() };
}
