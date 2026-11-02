# Shader workspace

The Studio navigation has a dedicated `#/shaders` route. It opens independently of
the template catalog, and lazy-loads its renderer so the gallery and editor do not
load shader code on startup. The workspace replaces the template side panel with
its own searchable collection, canvas, and controls. Mobile navigation includes the
same destination.

## Source and licensing

Research identified the original [Paper Shaders](https://github.com/paper-design/shaders)
as the exact source of all 30 requested effects and presets. Both
`@paper-design/shaders` and `@paper-design/shaders-react` are pinned to **0.0.82**,
whose package license is Apache-2.0. This release permits use in design tools.
Older search results referring to a restrictive license do not describe this release.

The original `LICENSE` and `NOTICE` are distributed in
`frontend/public/shaders/licenses/`. The original flower picture and the 30 gallery
previews are bundled from upstream commit
`1923e9f536ea079e2a95d23291cbfacfd69d37f6`; see the asset directory's README.
The UI also links to the original project. Rendering does not fetch code or sample
images from external services.

## Implementation

- `frontend/src/studio/shaders/catalog.ts`: exact upstream components and named presets;
  control labels, groups, enum options, and ranges. Default grain and glass-margin values
  follow the supplied parameter notes rather than newer upstream defaults. Colors retain
  upstream ordering (the reference panel lists some palettes in reverse order).
- `Controls.tsx`: normalized numbers display as percentages; angles and counts keep
  their units. Colors include alpha. Paper crumples and radial distortion can be enabled
  separately. Suggested ranges expand to accommodate upstream presets that exceed them.
- `Preview.tsx`: one WebGL canvas at a time, at the exact chosen output dimensions,
  visually scaled into the available space. Still shaders stop their animation loop.
  Logo uploads use upstream's mask preprocessing. Reduced-motion preferences pause
  animation initially. Unsupported WebGL and lost contexts have an explanatory state.
- `ShaderPage.tsx`: source uploads, per-effect edits during the session, current-draft
  persistence, preset switching that preserves pictures, and export actions.
- `files.ts`: validated draft import/export with embedded source pictures; canvas PNG
  capture. Storage failure is surfaced so a portable settings file can be saved.
- `recording.ts`: native canvas capture and MediaRecorder WebM export, with cancellation,
  hidden-tab detection, and stream/timer cleanup. The MIT-licensed
  [fix-webm-duration](https://github.com/yusitnikov/fix-webm-duration) package (1.0.1)
  adds the missing duration metadata before download; its license is also bundled.

**Add to images** uses the existing collision-safe image upload API. The saved PNG
appears in the same image picker used by templates; no new backend or rendering
service is required. Animated WebM files are downloaded separately. Video export
records in real time and its frame rate depends on the device's rendering performance.

## Verification

`npm --prefix frontend run lint`, `npm --prefix frontend run build`, and the frontend
tests cover routing, navigation, all 30 catalog entries, reference defaults, every
upstream preset's settings round trip, unit conversions, optional groups, draft
restoration, image preservation, and recording cleanup.

Real-browser verification should also render every effect, upload a picture and a
transparent logo, export PNG/settings/WebM, reopen settings, add a frame to images,
and inspect desktop and mobile layouts. The renderer requires a real WebGL 2 browser;
the component tests replace only that canvas layer.
