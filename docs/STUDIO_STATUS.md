# Template Studio verification

Checked on Windows on 2026-10-28. This is the first working Studio build.

## Delivered

- Six template families, 29 ready-to-edit gallery presets, four aspect ratios.
- Schema forms, asset uploads, themes, poster/storyboard previews, saved projects,
  background export queue and cancellation, and Author mode.
- Bundled static fonts and 313 icons. Windows rendering uses Fontconfig so the
  bundled weights work consistently without reloading each font for every text.
- Authenticated HTTP MCP and a stdio bridge sharing the running app's service.
- Windows portable desktop build; details and runtime checks in
  [desktop/VALIDATION.md](../desktop/VALIDATION.md).

## Checked

- Frontend lint and production build pass; 83 Studio tests pass.
- 58 service/API/worker tests and seven MCP/session tests pass.
- 57 template contract tests pass, including posters of all 29 presets in two aspects.
- Five additional layout regression checks pass. Corrected-font storyboard samples
  cover announcement, recap, quiz, celebration and quote templates.
- Real poster, cached preview, storyboard and draft MP4 export pass. A warm poster
  measured 566 ms; the short draft export measured 7.8 s in the last local run.
- Browser: edit sale text, auto-save project, preview, export and observe completed MP4.
  The 8.5-second vertical draft rendered in approximately 11 seconds and decoded correctly.
- Official MCP clients: create project, receive storyboard image, export PNG, poll
  completion, reject invalid template, and read the same projects through stdio.
- The stdio bridge also runs with the isolated desktop Python runtime.
- Transparent PNG checked as RGBA with alpha range 0–255.

## Existing test-environment failures

The broader backend run reports 938 passes, 15 skips and two failures that also
occurred before MCP integration: `test_temp_paths_printed_by_user_code_are_kept_where_they_name_nobody`
and `test_glued_redaction_leaves_longer_paths_and_urls_alone`. Both assume temporary
paths do not also match a user's home directory, which this Windows environment does.
The full frontend run reports 633 passes and one existing KaTeX version-check failure:
the local installed package is 0.16.47 while the test expects the declared 0.19 range.
Focused Studio checks and lint/build pass.

## Release work

The desktop output is unsigned and portable. Installer prerequisites, signing,
automatic updates, clean-machine acceptance, macOS and Linux remain release work.
Transparent video imports in third-party editors have not been exhaustively tested.
Template validation does not cover every possible combination of maximum content,
locale, uploaded image, background and social safe zone.

Sports posts, audiograms, route maps and the rest of the brainstorm remain future
template families. They are not included in this first gallery.
