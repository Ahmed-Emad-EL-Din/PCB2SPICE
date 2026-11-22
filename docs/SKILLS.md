# SKILLS.md — AI Skills for Building Professional Web Apps (GitHub inventory)

> Compiled 2026-11-22 from public GitHub/web sources. **Scope note:** skills are *agent behavior packs* (Claude Code / Cursor / Codex-style). They cannot be installed into this Arena session — they are the recommended **development toolkit** for this repository, and their rules are already reflected in `plan.md`. Install them on the dev machine(s) used to build this app.
>
> Recommended install paths: `npx skills add <git-url> --skill <name>` (skills CLI), manual `git clone <repo>` → copy skill dir to `~/.claude/skills/`, or Claude Code `/plugin marketplace add anthropics/claude-code` + `/plugin install …`. Verify each repo's LICENSE before redistribution — skills are inspirational prompt libraries, **do not copy their text into our code**.

---

## 1. Official Anthropic skills — `github.com/anthropics/skills` (★ ~22k)

Install: `/plugin marketplace add anthropics/claude-code` then pick, or `npx skills add https://github.com/anthropics/skills --skill <name>`.

| Skill | What it does | Where we use it |
|---|---|---|
| **frontend-design** | Distinctive production-grade UI; kills "AI slop" (generic purple-gradient blandness); strong typographic/aesthetic direction | All frontend phases (T-601…T-609, T-106). **Core install #1** |
| **web-artifacts-builder** | Multi-file React + Tailwind + shadcn/ui apps, not toy snippets | Frontend architecture decisions; component scaffolding |
| **webapp-testing** | Playwright-driven verification of your running app; agent clicks through flows, checks state, screenshots | T-608 E2E golden-path; every milestone M5/M6 sign-off |
| **mcp-builder** | Building MCP servers for APIs/tools | Optional: expose extraction engine as MCP (PCB-aware Copilot) — Phase 8 candidate |
| **skill-creator** | Create/evaluate new skills | Authoring org-specific skills later (e.g. "qspice-netlist-safety") |
| **document-skills (pdf/docx/pptx/xlsx)** | Generate Word/Excel/PDF/PowerPoint artifacts | T-405 report generation (PDF) & export-to-Excel parasitic tables |
| **algorithmic-art / canvas-design** | Generative visuals | Marketing site only (optional) |

## 2. Vercel agent-skills — `github.com/vercel-labs/agent-skills` (★ ~19.5k)

Install: `git clone https://github.com/vercel-labs/agent-skills.git` → copy `skills/<name>` to `~/.claude/skills/`.

| Skill | What it does | Where we use it |
|---|---|---|
| **web-design-guidelines** | 100+ rules: accessibility, UX, contrast, motion, forms — a *quality gate* | Pre-release audit (T-609/T-705); WCAG AA gate |
| **react-best-practices** | 57 rules / 8 categories: RSC boundaries, data-fetching, bundle, waterfalls | Frontend architecture review (T-601) |
| **composition-patterns** | Compound components, slots, avoiding boolean-prop hell | Design system work (T-106) |
| **web-design-reviewer** *(if present in repo)* | Design critique loop | Design iteration with stakeholders |

## 3. Community & domain skills (GitHub, verified this research)

| Skill / repo | Purpose | Verdict |
|---|---|---|
| **nextlevelbuilder/ui-ux-pro-max-skill** (★ ~30k) | Design intelligence: 50 styles, 97 palettes, 9 stacks (React/Next/Vue/Svelte/Tailwind); recommends palette+type per product | Use for T-106 design tokens — pick one direction, don't mix |
| **Addy Osmani — web-quality-skills** | Performance, SEO, accessibility audits; "reads like a report" | Pre-release performance gate (T-609/T-704). Find via `travisvn/awesome-claude-skills` listing (repo not pinned here; verify before install) |
| **K-Dense-AI/claude-scientific-skills** | Scientific computing skills (numerical methods, data analysis, plotting) | Extraction engine work (Phase 3) — notebooks, fitting, matrix audits |
| **obra/superpowers** | Engineering discipline: brainstorm → write-plan → TDD → review → ship | Team workflow backbone (entire plan.md) |
| **mattpocock/skills** (`grill-me`) | Interview-the-user skill; surfaces hidden assumptions | T-008 stakeholder review — literally run `grill-me` on README/plan |
| **lackeyjb/playwright-skill** | Playwright browser automation for agents | Alternative/complement to `webapp-testing` (T-608) |
| **travisvn/awesome-claude-skills** | Curated index of skills & marketplaces | Discovery hub — check before adding any new skill |
| **BbgnsurfTech/claude-skills-collection** | Mirrors official + community repos incl. `claude-scientific-skills`, `playwright-skill`, `ffuf` | Mirror/fallback source |
| **alirezarezvani/claude-skills** | 42+ domain-expert packs (incl. software architecture) | Architecture review for Phase 5 (T-501…T-506) |
| **jeremylongshore/claude-code-plugins-plus** | 240+ plugin hub / 185 skills | Plugin marketplace alternative |
| **simonw/claude-skills** | Code-interpreter-flavored skills (Simon Willison) | Data-analysis notebooks for validation (T-309) |
| **pec/anthropic Claude security-code-review** — official `claude-code-security-review` / `/security-review` | Pre-PR vulnerability scan | T-705 release gate |

## 4. Suggested install manifest (dev machines)

```bash
# --- Core (everyone) ---
npx skills add https://github.com/anthropics/skills --skill frontend-design
npx skills add https://github.com/anthropics/skills --skill webapp-testing
npx skills add https://github.com/anthropics/skills --skill web-artifacts-builder
git clone --depth 1 https://github.com/vercel-labs/agent-skills.git /tmp/vas && \
  cp -r /tmp/vas/skills/web-design-guidelines ~/.claude/skills/ && \
  cp -r /tmp/vas/skills/react-best-practices  ~/.claude/skills/ && \
  cp -r /tmp/vas/skills/composition-patterns  ~/.claude/skills/
git clone --depth 1 https://github.com/obra/superpowers.git ~/.claude/skills/superpowers

# --- Design ---
git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git ~/.claude/skills/ui-ux-pro-max

# --- Science/numerics ---
git clone --depth 1 https://github.com/K-Dense-AI/claude-scientific-skills.git ~/.claude/skills/claude-scientific-skills

# --- Optional ---
git clone --depth 1 https://github.com/lackeyjb/playwright-skill.git ~/.claude/skills/playwright-skill
# security review: enable built-in /security-review in Claude Code (official)
```

## 5. How each skill plugs into the plan (mapping)

| Phase | Skills applied |
|---|---|
| 0 Research / planning | `grill-me` (T-008), `superpowers` write-plan, `awesome-claude-skills` discovery |
| 1 Product/UX | `frontend-design`, `ui-ux-pro-max`, `composition-patterns`, `web-design-guidelines` |
| 2 Ingestion | `claude-scientific-skills` (binary parsing rigor), `superpowers` TDD |
| 3 Extraction engine | `claude-scientific-skills`, `superpowers` TDD + review, `simonw/claude-skills` (analysis) |
| 4 Injection/report | `document-skills` (pdf/xlsx), `superpowers`, human QSPICE review |
| 5 Backend | `alirezarezvani` architecture pack, `web-design-guidelines` (API ergonomics not applicable — but error UX is), `/security-review` |
| 6 Frontend | `frontend-design`, `web-artifacts-builder`, `react-best-practices`, `web-design-guidelines`, `webapp-testing`, `playwright-skill` |
| 7 Production | `webapp-testing` full regression, `/security-review`, `web-quality-skills` (perf), `web-design-guidelines` (a11y) |
| 8 Extensions | `mcp-builder`, `skill-creator` (author `qspice-pcb-engine` skill for power users) |

## 6. Process discipline this project adopts (from `superpowers` + Anthropic guidance)

1. **Brainstorm → plan → code** — no implementation without an approved `plan.md` task (violations = stop & re-plan).
2. **TDD for the engine** — extraction tests written before solver wrapper exists (golden geometries, §7 RESEARCH.md).
3. **Evidence over eloquence** — every claim in UI/report carries solver/formula/provenance; no "trust me" numbers.
4. **Verification runs** — `webapp-testing` smoke on every PR; full Playwright suite nightly; `/security-review` before any release tag.
5. **Design review** — `web-design-guidelines` checklist signed off at M6/M7.
6. **Small, reviewable diffs** — one task ID per PR; commit references `T-xxx`.

## 7. What we will NOT do

- Copy skill text verbatim into the codebase (license hygiene).
- Install unvetted skills from unknown accounts — only official (Anthropic/Vercel) or stars>1k community with visible maintenance.
- Let any skill "auto-approve" a release — humans sign off M5/M6/M7 gates.
- Ship UI generated in one shot by AI without the checklist pass (that's exactly what `web-design-guidelines` + `webapp-testing` exist to prevent).
