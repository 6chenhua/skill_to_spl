# PROJECT KNOWLEDGE BASE: skills/

**Purpose**: Example skill packages demonstrating the skill-to-cnlp pipeline

**Role**: Test cases and reference implementations for SPL/CNL-P transformation

---

## OVERVIEW

The `skills/` directory contains self-contained skill packages that serve as both test cases and reference implementations for the skill-to-cnlp pipeline. Each skill demonstrates how to structure documentation, code, and examples for transformation into SPL (Skill Processing Language) specifications.

---

## STRUCTURE

```
skills/
├── pdf/                    # PDF manipulation (extract, merge, split, forms)
├── docx/                   # Word document processing
├── pptx/                   # PowerPoint manipulation
├── xlsx/                   # Excel spreadsheet operations
├── canvas-design/          # HTML5 Canvas design
├── brand-guidelines/       # Brand identity guidelines
├── skill-to-cnlp/          # The SPL emitter skill itself (meta)
├── theme-factory/          # Color theme generation
├── ui-ux-pro-max/          # UI/UX design system
├── skill-creator/          # Skill creation helper
├── algorithmic-art/        # Generative art creation
├── claude-api/             # Claude API integration
├── doc-coauthoring/        # Document collaboration
├── frontend-design/        # Frontend design patterns
├── internal-comms/         # Internal communications
├── mcp-builder/            # MCP server builder
├── slack-gif-creator/      # Slack GIF generation
├── web-artifacts-builder/  # Web artifact generation
└── webapp-testing/         # Web application testing
```

---

## WHERE TO LOOK

| Skill Type | Directory | Key Files |
|------------|-----------|-----------|
| Document processing | `pdf/`, `docx/`, `pptx/`, `xlsx/` | SKILL.md, scripts/, reference.md |
| Design and creative | `canvas-design/`, `theme-factory/`, `ui-ux-pro-max/`, `brand-guidelines/` | SKILL.md, themes/, data/ |
| Meta skills | `skill-to-cnlp/`, `skill-creator/` | SKILL.md, references/, agents/ |
| API integration | `claude-api/`, `mcp-builder/` | SKILL.md, scripts/ |
| Communication | `slack-gif-creator/`, `internal-comms/` | SKILL.md, assets/ |
| Testing | `webapp-testing/` | SKILL.md, scripts/ |

---

## SKILL PACKAGE ANATOMY

Each skill package follows a consistent structure:

```
skill-name/
├── SKILL.md              # Canonical documentation with YAML frontmatter
├── scripts/              # Implementation files (.py, .js, etc.)
├── docs/                 # Supplementary documentation (optional)
├── examples/             # Usage examples (optional)
├── references/           # Reference documentation (optional)
├── LICENSE.txt           # License terms
└── *.md                  # Additional markdown docs (forms.md, etc.)
```

### SKILL.md Frontmatter

Every SKILL.md starts with YAML frontmatter:

```yaml
---
name: skill-name
description: Clear description of when to use this skill
license: Proprietary. LICENSE.txt has complete terms
---
```

### Key Sections in SKILL.md

- **Overview**: What the skill does and when to use it
- **Quick Start**: Minimal working example
- **Core Capabilities**: Main features and workflows
- **Implementation Details**: Technical specifics
- **Examples**: Real-world usage patterns

---

## CONVENTIONS

### File Naming
- Use `kebab-case` for directory names (`skill-creator/`, not `skill_creator/`)
- SKILL.md is always uppercase
- Supporting docs use lowercase with descriptive names (`forms.md`, `reference.md`)

### Documentation Style
- Start with YAML frontmatter containing name, description, license
- Use clear hierarchical headings (## Overview, ## Quick Start)
- Include code examples in fenced blocks with language tags
- Reference external files with relative paths

### Scripts Organization
- Place implementation files in `scripts/` subdirectory
- Python files use `snake_case.py`
- JavaScript files use `camelCase.js` or `kebab-case.js`
- Include docstrings and type hints where applicable

### Cross-References
- Reference other docs with relative paths: "see REFERENCE.md"
- Link to specific sections: "see FORMS.md for form filling"
- Include license reference in frontmatter and footer

---

## ANTI-PATTERNS

**NEVER** omit the YAML frontmatter in SKILL.md. The pipeline requires it for metadata extraction.

**NEVER** mix implementation files at the root level. Always use `scripts/` subdirectory.

**NEVER** use absolute paths in documentation. All references must be relative to the skill root.

**AVOID** duplicating content across multiple markdown files. Use references and links instead.

**NO** hardcoded credentials or API keys in any skill files.

**NEVER** assume external dependencies are installed. Document requirements clearly.

---

## KEY SKILLS REFERENCE

### pdf/
PDF manipulation toolkit covering extraction, merging, splitting, form filling, encryption, and OCR. See `reference.md` for advanced features.

### docx/
Word document processing with python-docx. Handles document creation, styling, tables, and OOXML manipulation.

### pptx/
PowerPoint generation and editing. Supports slide creation, templating, and conversion from HTML.

### xlsx/
Excel spreadsheet operations including formulas, charts, and data validation.

### skill-to-cnlp/
The meta-skill that defines the SPL grammar itself. Contains the canonical REFERENCE.md for SPL syntax.

### skill-creator/
Helper skill for creating new skills. Includes templates and validation tools.

---

## NOTES

- Skills are processed by the pipeline in `../pipeline/`
- Output goes to `../output/{skill-name}/`
- Each skill must be self-contained and independently testable
- The pipeline extracts structure from SKILL.md and code from scripts/
