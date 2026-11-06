# M1 browser and implementation verification

Date: 2026-10-14, Asia/Shanghai. Local development only.

## Environment and commands

- Python3.14.4 in backend/.venv; dependencies pinned in requirements.lock.
- Node24.19.0/pnpm11.25.0; React18.3.1, Vite7.0.0, Vitest3.2.6. esbuild build permission explicitly scoped in pnpm-workspace.yaml.
- Backend `python -m unittest discover -s backend/tests -v`:28/28 passed.
- Frontend `pnpm --dir apps/web test --run`:7/7 passed; `build`:TypeScript+Vite passed.
- Research `python -m unittest discover -s research/tests -v`:5/5 passed; no full audit rerun or model training claimed.
- Dedicated Browser plugin skill was unavailable. Used the available CUA in-app browser API for real UI checks and its documented CDP capability for network/media/mouse emulation, rather than inferring behavior from source or a build.

## Observed behavior

| Check | Actual observation |
|---|---|
| First open | Source revenue2103585508.31 CNY,365d, consolidated; q blank; no calculated amount or fake history |
| Calculate | q80%,delay15d →69158975.62 CNY, backend authoritative |
| Source | ExcerptP69, unit/headerP64; pending independent review and historical availability preserved |
| PDF bytes | Real HTTP200,1314153 bytes, SHA matches registered62eaa4d6…; PDF request bound to expected saved SHA |
| Drawer | Modal focuses close; Esc closes; focus returns to source button |
| Compare | Same-q zero-delay baseline difference69158975.62; saved identical scenario difference0.00; table and why panel show inputs/source/formula, no causal decomposition |
| Chart | Actual backend points; equivalent numeric table expands; keyboard can reach nodes |
| Draft edit |15→20d marks old result and disables save; restore resets parameters |
| Save/reopen | API-created records appear in history; reopen restores amount/q/delay/title; three clearly named demo records retained in local ignored SQLite |
| Offline calculation | Request fails visibly; retry after network restoration succeeds |
| Offline save | Failed request does not show success; retry uses same Idempotency-Key b8c59dc0…; only one new saved record |
| Narrow viewport |390px setting and normal narrow panel tested; no horizontal page overflow, layout stacks |
| Keyboard | Enter calculates; modal Esc/focus restore works; graph points reachable |
| Hover | Real mouse movement produces lift/scale/shadow transition on enabled calculation button |
| Reduced motion | Emulated prefers-reduced-motion reduce:computed transform none,transition none; setting restored |
| Normal console | No warning/error before intentionally simulated network failure; expected network errors were caused by offline QA |
| Missing sources | Isolated copied DB, missing corporate root, API8011/web5175:history opens original69158975.62,calculation/save disabled, explicit source warning; drawer omits local link and explains missing file. Temporary tab/services closed |

Screenshots are local QA artifacts outside the repository: `D:/留学准备/m1-desktop-qa.png`, `m1-mobile-qa.png`, `m1-history-source-missing-qa.png`, final `m1-final-preview.png`. Screenshot evidence is supplementary; API/reducer tests cover financial/transaction/version boundaries.

## Independent review fixes

1. Old source ID no longer resolves to new registered bytes without matching saved SHA. Current availability fetched separately; PDF endpoint rechecks bytes on each request.
2. Saving includes expected_input_hash, preserving replay lookup before current source resolution. New mismatched calculations reject409; frontend also refuses to mark another identity saved.
3. Invalid/missing current source configuration permits history-only startup; frontend can browse stored snapshots without an active case.
4. Comparison engine mismatch gives an explicit version message instead of endless loading.

Each regression was observed failing before fixing. Full suites then passed. An earlier Windows SQLite locked-file problem was fixed by explicitly closing connections instead of relying on the transaction context manager.

## Limits and next steps

- Single-user loopback app, not a remote deployment. Original projects remain read-only.
- Annual uniform-sales sensitivity, not weekly cash forecasting or default probability. Original source still pending independent human review; current SHA equality is a version check.
- Real touch hardware and other browsers not tested. Some small text/control density and native English network errors can be refined after user feedback.
- Cashflow/training UI are explicitly marked planned. No new neural model, paid calls or model download.
- Next research slice: reliable support/confounder/unknown label policy, reproducible ranking baseline and hardware check before training. Cashflow scenario work uses separately modeled synthetic events.
