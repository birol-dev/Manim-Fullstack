// The same source photograph is passed into each real Paper image shader.
export const natureSource = 'assets/nature-river.webp';
export const imageEffects = {
  glass: { name: 'Fluted Glass', file: 'fluted-glass', shader: 'flutedGlassFragmentShader', note: 'Ribbed glass and refracted light', family: 'Light & glass' },
  lens: { name: 'Lens Distortion', file: 'lens-distortion', shader: 'lensDistortionFragmentShader', note: 'Soft distortion and split color', family: 'Light & glass' },
  water: { name: 'Water', file: 'water', shader: 'waterFragmentShader', note: 'Ripples across your image', family: 'Light & glass' },
  paper: { name: 'Paper Texture', file: 'paper-texture', shader: 'paperTextureFragmentShader', note: 'Paper grain, fibers, and folds', family: 'Paper & print' },
  dots: { name: 'Halftone Dots', file: 'halftone-dots', shader: 'halftoneDotsFragmentShader', note: 'Your image as a dot print', family: 'Paper & print' },
  cmyk: { name: 'Halftone CMYK', file: 'halftone-cmyk', shader: 'halftoneCmykFragmentShader', note: 'A four-color print effect', family: 'Paper & print' },
  dither: { name: 'Image Dithering', file: 'image-dithering', shader: 'imageDitheringFragmentShader', note: 'Limited color with a pixel texture', family: 'Paper & print' },
};

export function imageUniforms(engine, image, effect, strength = 0.65, scale = 1) {
  const color = engine.getShaderColorFromString;
  const base = { u_image: image, u_fit: 2, u_scale: scale, u_rotation: 0, u_offsetX: 0, u_offsetY: 0,
    u_originX: 0.5, u_originY: 0.5, u_worldWidth: 0, u_worldHeight: 0 };
  if (effect === 'glass') return { ...base, u_colorBack: color('#15352d'), u_colorShadow: color('#112c27'),
    u_colorHighlight: color('#ffffff'), u_shadows: strength * 0.14, u_highlights: strength * 0.12,
    u_size: 0.5, u_angle: 0, u_shape: 1, u_distortionShape: 1, u_distortion: strength * 0.65,
    u_shift: 0, u_stretch: 0, u_blur: 0, u_edges: 0.1, u_marginLeft: 0, u_marginRight: 0,
    u_marginTop: 0, u_marginBottom: 0, u_grainMixer: 0, u_grainOverlay: strength * 0.025 };
  if (effect === 'water') return { ...base, u_colorBack: color('#15352d'), u_colorHighlight: color('#d9fff4'),
    u_highlights: strength * 0.08, u_layering: strength * 0.25, u_waves: strength * 0.55,
    u_edges: strength * 0.4, u_caustic: strength * 0.2, u_size: 0.9 };
  if (effect === 'lens') return { ...base, u_spread: strength * 0.16, u_bias: 0, u_angle: 140,
    u_perspective: 0.65, u_count: 12, u_dispersion: 0.3, u_dispersionShift: 0,
    u_dispersionColor: 0, u_focusCenter: 0.65, u_focusEdges: 0, u_swirl: 0,
    u_noise: 0, u_noiseFrequency: 0.2, u_noiseOffset: 0, u_lensBulge: strength * 0.2,
    u_lensCircle: 0, u_grainMixer: 0, u_grainOverlay: strength * 0.035, u_imageX: 0, u_imageY: 0 };
  if (effect === 'dots') return { ...base, u_colorFront: color('#24483b'), u_colorBack: color('#f4f0e4'),
    u_originalColors: true, u_type: 0, u_inverted: false, u_grid: 1,
    u_size: 0.12 + strength * 0.3, u_radius: 1, u_contrast: 0.65, u_grainMixer: 0,
    u_grainOverlay: strength * 0.05, u_grainSize: 0.3 };
  if (effect === 'dither') return { ...base, u_colorFront: color('#274b3a'), u_colorBack: color('#f2eddd'),
    u_colorHighlight: color('#b5c5a1'), u_type: 3, u_pxSize: 1 + strength * 3,
    u_colorSteps: 7 - strength * 4, u_originalColors: true, u_inverted: false };
  if (effect === 'cmyk') return { ...base, u_colorBack: color('#f4f0e4'),
    u_colorC: color('#008b9b'), u_colorM: color('#d15b83'), u_colorY: color('#f5cb63'), u_colorK: color('#233b32'),
    u_size: 0.08 + strength * 0.2, u_contrast: 1, u_softness: 0.2, u_grainSize: 0.2,
    u_grainMixer: strength * 0.05, u_grainOverlay: strength * 0.08, u_gridNoise: 0.05,
    u_floodC: 0, u_floodM: 0, u_floodY: 0, u_floodK: 0,
    u_gainC: 0, u_gainM: 0, u_gainY: 0, u_gainK: 0, u_type: 0,
    u_noiseTexture: engine.getShaderNoiseTexture() };
  return { ...base, u_isImage: true, u_colorBack: color('#ece5d4'), u_colorPaper: color('#fff5dc'),
    u_colorShadow: color('#8c846b'), u_blending: 1, u_distortion: strength * 0.5, u_clip: false,
    u_angle: 300, u_seed: 4, u_roughness: strength * 0.4, u_roughnessSize: 0.5, u_roughnessRows: 0,
    u_fiber: strength * 0.45, u_fiberSize: 0.5, u_folds: strength * 0.6, u_foldSizeX: 1,
    u_foldSizeY: 1, u_foldOffsetX: 0, u_foldOffsetY: 0, u_wrinkles: strength * 0.7,
    u_wrinkleSize: 0.65, u_crumples: 0, u_crumpleCount: 6, u_drops: 0,
    u_noiseTexture: engine.getShaderNoiseTexture() };
}
