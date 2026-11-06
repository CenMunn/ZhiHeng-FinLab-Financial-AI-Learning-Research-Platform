# Frontend redesign: FlyLoop interaction × investment research styling

User feedback: the first light dashboard did not reflect the requested interaction design or visual quality. This revision replaces its app shell and composition, while preserving trusted calculations, source/version binding and saved records.

## Reference and design

- Read FlyLoop's actual Flywheel, PlanPage and styles: clickable stages, task focus/navigation, persistent selected state, contextual details. Reimplemented four business stages; did not copy the learning application's six-stage semantics or progress approximation.
- Inspected the running 智投委AI at localhost3151/filings and its research home. Read its local visual tokens. Borrowed dark ink surfaces, mint actions and gold accents; did not modify either reference project or copy their branding.
- Applied Interactive-front-end and its microinteraction guidance, Frontend Design, Frontend App Builder, React best practices and frontend testing/debugging. User's earlier delegation of first visual choice and current explicit redesign instruction authorize implementation without another routine permission gate.
- Generated a full-screen concept before coding. Concept: `C:/Users/g'g/.codex/generated_images/01a12173-6705-7990-a07f-2c0f9e6f614f/exec-2f7ebfa6-e850-4a5d-abc4-b7cf8d9540bf.png`.
- Tokens: canvas#080d13,surface#121a23/17212b,line#283641,text#e9f0f3,muted#91a0ac,mint#72d4b0,gold#dbbd78. Typography: Chinese system UI family, deliberate display scale, tabular financial numbers, explicit form/control sizes. No bitmap screenshot shipped as interface.

## Ownership

| Module | Owns | Does not own |
|---|---|---|
| App + HistoryDrawer | Navigation, history fetching/filtering/opening | Financial calculation |
| useRiskScenario | Existing request/revision/idempotency boundaries and pending-open confirmation | Layout or new formulas |
| ResearchWheel | Source/assumption/projection/archive navigation and real labels | Fake completion percentages |
| AssumptionPanel | Input, presets, slider, compute trigger | Browser-side financial arithmetic |
| SensitivityChart | Plotting server curve, hover/focus readout, setting draft delay | Treating a draft as computed |
| ComparisonPanel | Same-basis result/parameter comparison and explanation | Causal attribution |
| ModalFrame | Native modal lifecycle, Escape, focus restoration | Business state |

## Concept-to-render ledger

| Inspected point | Initial mismatch | Resolution / intentional difference |
|---|---|---|
| Layout | Wheel too small; central curve made page too tall | Enlarged ring framing, adjusted wide-screen columns, reduced plot height |
| Palette | Old pale surfaces and blue accents | Replaced shared tokens and all workbench/dialog surfaces with dark/mint/gold system |
| Typography | Old9–11px-heavy metadata; weak heading/number hierarchy | Wide-screen48px headline,56px output,30px inputs; explicit UI scale and mobile reading line |
| Controls | Save action and contextual views buried in vertical cards | Central curve/comparison tabs; fixed adjacent hypothesis inspector; shallow save bar |
| Icons | Orbit styles accidentally applied to icon child paths | Scoped sector rules to direct path; comparison uses split-column icon |
| Motion | Hover effect confined to primary actions | Wheel sectors lift outward, presets/buttons lift/press, graph hover/crosshair/readout, history cards respond |
| Copy/state | Concept invented generic source “完成” and three historical records | Source says已登记/待独立复核; real record count4; initial q stays blank; status follows state |
| Responsive | SVG tooltip text would shrink too far on mobile | Mobile HTML value readout, larger chart axis text; input before chart; no page overflow |

Allowed primary copy checked: 财务风险研究台、企业风险推演、现金流沙盘、训练评测、历史情景、回款压力推演、研究标的、来源与观察、敏感性曲线、情景对比、设置回款假设、计算情景、保存这次推演、保存情景. Business-required instructions, pending quality and stale-result messages intentionally take precedence over generic generated captions. Brand subline is 从财报证据出发; no assertion of identifying “真实风险”.

Both concept and latest implementation screenshot inspected using view_image in the same final QA pass. Layout, palette, typography, controls, chart, source rail and real-state differences were checked. This records fidelity to the selected direction; aesthetic acceptance remains the user's judgment.

## Runtime checks

- Browser: CUA in-app browser documented APIs, localhost5174;1600×1000 concept-scale,1440×900 and390×844 checked. Native full-page screenshot used; temporary metrics override and an unreliable tiled capture were discarded after correcting the selected tab/viewport. All overrides restored at handoff.
- q blank initially; no fabricated zero/curve. q80%,delay15 →69158975.62;30 →138317951.23. Comparing the actual saved15d scenario gives69158975.61 difference, calculated by the backend.
- Wheel资料 opens actual source modal;假设 focuses credit-share;推演 selects curve and focuses result;归档 focuses title. Escape/focus restoration checked.
- Preset30 changes draft and marks old result stale; save disabled until compute. Graph45 changes draft45 and disables saving; restore returns previous parameters.
- Keyboard ArrowRight switches curve to comparison; why panel shows source/assumptions/formula. Numeric table remains available.
- Actual save/reopen verified; one explicitly titled 深色版演示 · 30天回款延迟 record added. Search80% filters history. Cancel opening preserves70% draft; confirmation restores saved80%/15d.
- Saving initially jumped away from comparison; fixed by separating history-open version from save completion. This preserves the current reading view during save.
- Hovered primary button computed scale1.02/translateY(-3px); plot hover45 displayed207476926.85. Press has separate return/scale state. Reduced-motion computed transform none/transition none; media setting restored.
-390px: no horizontal overflow; primary calculate48px/save44px; presets adjusted to44px. Touch emulation command unsupported by IAB, so no true touch-device pass is claimed.
- Local dev processes stopped during tool/session interruption; restarted existing ports and confirmed API/proxy200. No data loss. Latest client was explicitly reloaded after module edits.
- Network/invalid-proxy error cases first failed frontend tests, then passed after Chinese actionable errors and preserved AbortError handling. Browser offline compute displayed the Chinese error; restoring network allowed retry. Network emulation restored in finally.
- Final tests:9 frontend tests and production TypeScript/Vite build;28 backend regression tests. No trained model or new financial effect claimed.

Final screenshots: `D:/留学准备/m1-dark-final.png`, `D:/留学准备/m1-dark-mobile.png`. Other temporary screenshots are removed; existing previous-release artifacts are left alone.

Not covered: physical touch hardware and other browser engines. Cashflow and training navigation remain visibly disabled with explanatory titles.
