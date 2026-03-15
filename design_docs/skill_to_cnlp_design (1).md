# Skill-to-CNL-P Pipeline — 完整系统设计文档

---

## 总体架构

```
skill_root/
    │
    ├── P1 ──────────────────────────────────────────► FileReferenceGraph
    │    (纯代码: rglob + frontmatter解析 + 引用图构建)
    │
    ├── P2 ──────────────────────────────────────────► FileRoleMap
    │    (LLM: 基于引用语气推断各文件的读取优先级)
    │
    ├── P3 ──────────────────────────────────────────► SkillPackage
    │    (纯代码: 按优先级拼接文件内容 + 可选LLM摘要)
    │
    ├── Step 1 ───────────────────────────────────────► SectionBundle
    │    (LLM: merged_doc_text → 8个规范section分类)
    │
    ├── Step 2A ──────────────────────────────────────► list[RawClause]
    │    (LLM: 提取规范性语句 + 6维评分)
    │
    ├── Step 2B ──────────────────────────────────────► list[ClassifiedClause]
    │    (纯代码: 决策表分类 HARD/MEDIUM/SOFT/NON)
    │
    ├── Step 3 ───────────────────────────────────────► StructuredSpec
    │    (LLM: 从SectionBundle+ClassifiedClauses提取实体/步骤/接口)
    │
    └── Step 4 ───────────────────────────────────────► SPLSpec
         (LLM×5: 并行Round1 + 串行Round2，生成完整SPL文本)
```

---

## 数据结构定义

所有阶段共享以下核心数据结构：

```python
# ── P1 输出 ───────────────────────────────────────────────────────────────
@dataclass
class FileNode:
    rel_path: str               # 相对于skill_root的路径
    kind: Literal["doc", "script", "data", "asset"]
    size_bytes: int
    head_lines: list[str]       # 前5行（脚本）或前20行（文档）
    references: list[str]       # 该文件内部引用的其他文件名

@dataclass
class FileReferenceGraph:
    skill_id: str               # 取自skill_root目录名
    nodes: dict[str, FileNode]  # rel_path → FileNode
    edges: dict[str, list[str]] # referencing_file → [referenced_files]
    skill_md_content: str       # SKILL.md全文
    frontmatter: dict           # YAML frontmatter解析结果
    # 自动推导的能力清单（用于Step 2B降级）
    local_scripts: list[str]    # .py/.sh文件的rel_paths
    referenced_libs: list[str]  # import/require提取的库名

# ── P2 输出 ───────────────────────────────────────────────────────────────
@dataclass
class FileRoleEntry:
    role: Literal[
        "primary",          # SKILL.md（强制）
        "core_workflow",    # 被"MUST consult"/"see steps in X"引用
        "core_script",      # 被明确指名调用的脚本
        "supplementary",    # "see also"/"reference"级别引用
        "unknown"           # 无法判断
    ]
    read_priority: Literal[1, 2, 3]  # 1=全文 2=摘要 3=跳过
    must_read_for_normalization: bool
    reasoning: str          # 引用原句的一句话解释（verbatim引用片段）

FileRoleMap = dict[str, FileRoleEntry]  # rel_path → FileRoleEntry

# ── P3 输出 ───────────────────────────────────────────────────────────────
@dataclass
class SkillPackage:
    skill_id: str
    merged_doc_text: str        # 所有文件内容按优先级拼接后的单一文本
    # merged_doc_text中每个文件块的边界标记格式：
    # === FILE: {rel_path} | role: {role} | priority: {priority} ===
    # ...内容...
    # === END FILE: {rel_path} ===
    capability_profile: "CapabilityProfile"  # 从P1自动构建

@dataclass
class CapabilityProfile:
    # Layer 1：从P1自动推导（保守集合）
    local_scripts: list[str]    # 技能目录中存在的脚本
    referenced_libs: list[str]  # 被代码引用的Python/shell库
    # Layer 2：可选外部注入（调用方提供）
    available_tools: list[str]  # e.g. ["github_api", "docker"]
    runtime_env: Literal["local", "cloud", "mcp", "unknown"]

# ── Step 1 输出 ───────────────────────────────────────────────────────────
@dataclass
class SectionItem:
    text: str               # verbatim从merged_doc_text复制
    source: str             # 来源文件的FILE边界标记中的rel_path
    multi: bool             # 该section内容是否来自多个源文件

@dataclass
class SectionBundle:
    INTENT: SectionItem
    WORKFLOW: SectionItem
    CONSTRAINTS: SectionItem
    TOOLS: SectionItem
    ARTIFACTS: SectionItem
    EVIDENCE: SectionItem
    EXAMPLES: SectionItem
    NOTES: SectionItem      # 兜底：所有无法归类的内容

# ── Step 2A 输出 ──────────────────────────────────────────────────────────
@dataclass
class DimScores:
    O: int  # Observability       0-3
    A: int  # Actionability       0-3
    F: int  # Formalizability     0-3
    C: int  # Context-dependence  0-3
    R: int  # Risk criticality    0-3
    V: int  # Verifiability       0-3

@dataclass
class RawClause:
    clause_id: str          # 格式: "C{n:03d}"，e.g. "C001"
    original_text: str      # 从SectionBundle中verbatim提取
    source_section: str     # 来自哪个section（INTENT/WORKFLOW/...）
    source_file: str        # 来自哪个文件（rel_path）
    scores: DimScores
    is_normative: bool      # 是否含MUST/SHALL/NEVER等信号词
    split: bool             # 是否是混合语句被拆分后的子条款
    parent_clause_id: str | None  # split=True时指向父条款

# ── Step 2B 输出 ──────────────────────────────────────────────────────────
@dataclass
class ClassifiedClause(RawClause):
    classification: Literal[
        "COMPILABLE_HARD",
        "COMPILABLE_MEDIUM",
        "COMPILABLE_SOFT",
        "NON_COMPILABLE"
    ]
    S_det: int              # min(O, F, V)
    S_proc: int             # min(A, V)
    confidence: float       # 0.0-1.0，来自LLM输出
    needs_review: bool
    risk_override: bool     # R=3触发的强制升级
    downgraded: bool        # capability_profile触发的降级
    enforcement_backends: list[str]  # e.g. ["json_schema", "rego"]

# ── Step 3 输出 ───────────────────────────────────────────────────────────
@dataclass
class EntityProvenance:
    source: Literal["EXPLICIT", "ASSUMED", "LOW_CONFIDENCE"]
    source_text: str        # 支撑推断的原文片段（verbatim）
    source_file: str

@dataclass
class Entity:
    entity_id: str          # snake_case命名
    kind: Literal["Artifact", "Run", "Evidence", "Record", "Config"]
    type_name: str          # 用自然语言描述的类型，e.g. "JSON object"
    schema_notes: str       # 对字段结构的描述
    is_file: bool           # kind=Artifact且实际存在于磁盘
    file_path: str | None   # is_file=True时的路径（"< >"表示运行时上传）
    provenance: EntityProvenance

@dataclass
class WorkflowStep:
    step_id: str            # 格式: "S{n:02d}"
    description: str        # SPL-ready的步骤描述（自然语言）
    prerequisites: list[str]    # entity_ids（该步骤执行前必须存在）
    produces: list[str]         # entity_ids（该步骤产出的实体）
    effects: list[str]          # e.g. ["DISK_WRITE", "NETWORK", "LLM_CALL"]
    is_validation_gate: bool    # 来自EVIDENCE section，验证步骤
    tool_hint: str | None       # 来自TOOLS section的工具名称提示
    provenance: EntityProvenance

@dataclass
class InteractionRequirement:
    req_id: str
    description: str        # 需要用户输入的情形描述
    source_clause_id: str   # 对应的NON_COMPILABLE clause_id
    input_type: str         # e.g. "confirmation", "file_upload", "text"

@dataclass
class StructuredSpec:
    entities: list[Entity]
    workflow_steps: list[WorkflowStep]
    interaction_requirements: list[InteractionRequirement]
    success_criteria: dict  # {description, deterministic, source_text}
    needs_review_items: list[dict]  # [{item, reason, question}]
```

---

## P1 — Reference Graph Builder（纯代码）

### 职责

遍历skill_root目录，构建文件引用关系图，提取能力清单（capability manifest），为后续LLM步骤准备结构化的文件元数据。

### 输入

```
skill_root: Path  # 必须包含SKILL.md
```

### 处理逻辑

```python
def build_reference_graph(skill_root: Path) -> FileReferenceGraph:
    skill_id = skill_root.name
    nodes = {}
    edges = {}
    local_scripts = []
    referenced_libs = []

    # 1. 枚举所有文件，按扩展名分类
    EXT_KIND = {
        ".md": "doc", ".txt": "doc", ".rst": "doc",
        ".py": "script", ".sh": "script", ".bash": "script",
        ".json": "data", ".yaml": "data", ".yml": "data", ".csv": "data",
        ".png": "asset", ".jpg": "asset", ".svg": "asset", ".pdf": "asset",
    }
    for path in skill_root.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(skill_root))
            kind = EXT_KIND.get(path.suffix.lower(), "doc")
            size = path.stat().st_size

            if kind == "script":
                local_scripts.append(rel)
                with open(path) as f:
                    head = [f.readline() for _ in range(5)]
                # 提取import语句中的库名
                for line in head:
                    m = re.match(r"(?:import|from)\s+([\w.]+)", line.strip())
                    if m:
                        lib = m.group(1).split(".")[0]
                        if lib not in referenced_libs:
                            referenced_libs.append(lib)
                refs = []  # 脚本内部文件引用较少，暂不深度解析

            elif kind == "doc":
                with open(path) as f:
                    head = [f.readline() for _ in range(20)]
                # regex扫描文件名引用（markdown链接、括号引用等）
                content_preview = "".join(head)
                refs = re.findall(
                    r"(?:\[.*?\]\(|`|\"|\s)([a-zA-Z0-9_\-/]+\.\w+)",
                    content_preview
                )
                refs = [r for r in refs if not r.startswith("http")]
            else:
                head = []
                refs = []

            nodes[rel] = FileNode(
                rel_path=rel, kind=kind, size_bytes=size,
                head_lines=head, references=refs
            )
            if refs:
                edges[rel] = refs

    # 2. 读取并解析SKILL.md frontmatter
    skill_md_path = skill_root / "SKILL.md"
    if not skill_md_path.exists():
        raise ValueError(f"SKILL.md not found in {skill_root}")
    skill_md_content = skill_md_path.read_text()

    frontmatter = {}
    fm_match = re.match(r"^---\n(.*?)\n---", skill_md_content, re.DOTALL)
    if fm_match:
        import yaml
        frontmatter = yaml.safe_load(fm_match.group(1)) or {}

    # 3. 构建capability_profile（Layer 1）
    capability_profile = CapabilityProfile(
        local_scripts=local_scripts,
        referenced_libs=referenced_libs,
        available_tools=[],       # Layer 2由调用方注入
        runtime_env="unknown"
    )

    return FileReferenceGraph(
        skill_id=skill_id,
        nodes=nodes, edges=edges,
        skill_md_content=skill_md_content,
        frontmatter=frontmatter,
        local_scripts=local_scripts,
        referenced_libs=referenced_libs,
        capability_profile=capability_profile
    )
```

### 输出

`FileReferenceGraph`（见数据结构定义）

### 注意事项

- SKILL.md不存在则抛出异常，不继续执行
- 二进制文件（asset类）不读取内容，只记录元数据
- 所有head_lines保留原始编码，不做任何内容修改

---

## P2 — File Role Resolver（LLM）

### 职责

基于P1提取的文件摘要和引用关系，判断每个文件对normalization的重要程度（read_priority），决定哪些文件的内容需要被完整拼入SkillPackage。

### 输入

来自P1的`FileReferenceGraph`，提取以下字段传给LLM：

```python
def build_p2_input(graph: FileReferenceGraph) -> str:
    """构建传给LLM的压缩表示"""
    # 1. 从SKILL.md中提取包含其他文件名的句子（±1行上下文）
    skill_md_lines = graph.skill_md_content.splitlines()
    file_names = set(graph.nodes.keys())
    ref_sentences = []
    for i, line in enumerate(skill_md_lines):
        for fname in file_names:
            base = Path(fname).name
            if base in line and fname != "SKILL.md":
                ctx_start = max(0, i - 1)
                ctx_end = min(len(skill_md_lines), i + 2)
                ref_sentences.append({
                    "file": fname,
                    "context": "\n".join(skill_md_lines[ctx_start:ctx_end]),
                    "line": i + 1
                })
                break

    # 2. 所有nodes的摘要
    node_summaries = [
        {
            "path": path,
            "kind": node.kind,
            "size_bytes": node.size_bytes,
            "head_lines": node.head_lines[:3]  # 只取前3行
        }
        for path, node in graph.nodes.items()
        if path != "SKILL.md"  # SKILL.md强制primary，不经LLM
    ]

    return json.dumps({
        "skill_id": graph.skill_id,
        "ref_sentences": ref_sentences,
        "node_summaries": node_summaries,
        "edges": graph.edges
    }, ensure_ascii=False, indent=2)
```

### LLM Prompt

```
You are a document analyst. Your task is to determine the reading priority of files in a software skill package.

You will receive a JSON object with the following fields:
- `skill_id`: the name of the skill
- `ref_sentences`: sentences from the main instruction file that mention other files, with ±1 line of context
- `node_summaries`: metadata for each non-main file (path, kind, size_bytes, first 3 lines)
- `edges`: a map of which files reference which other files

Your goal: for each file in `node_summaries`, assign a `read_priority`:
- **1** (read in full): the file contains essential procedural or constraint content that cannot be understood without its full text. Signals: phrases like "MUST consult", "see steps in", "follow instructions in", "CRITICAL", "required reading", or the file is explicitly named as a prerequisite workflow.
- **2** (summarize): the file contains useful supplementary content but is referenced informally ("see also", "reference", "for details", "example"). Its head lines give enough context.
- **3** (skip): the file is an asset (image, PDF), a generated artifact, a lockfile, or is not referenced at all.

Output a JSON array. One object per file. No other text.

Schema for each object:
{
  "path": "<rel_path>",
  "role": "core_workflow" | "core_script" | "supplementary" | "unknown",
  "read_priority": 1 | 2 | 3,
  "must_read_for_normalization": true | false,
  "reasoning": "<verbatim quote from ref_sentences that justifies this decision, max 1 sentence; if not found in ref_sentences, write 'not explicitly referenced'>"
}

Rules:
- If a file appears in `node_summaries` but not in any `ref_sentences`, assign priority 3 unless its `kind` is "script" and it appears in `edges` as a dependency of a priority-1 file.
- Binary/asset files always get priority 3.
- Do not invent reasons. `reasoning` must be a direct quote or "not explicitly referenced".
- Output valid JSON only. No markdown, no explanation.

Input:
{p2_input_json}
```

### P2后处理（纯代码）

```python
def build_file_role_map(
    llm_output: str,
    graph: FileReferenceGraph
) -> FileRoleMap:
    result = json.loads(llm_output)
    role_map: FileRoleMap = {}

    # 强制注入SKILL.md
    role_map["SKILL.md"] = FileRoleEntry(
        role="primary",
        read_priority=1,
        must_read_for_normalization=True,
        reasoning="SKILL.md is the primary instruction file (forced by system)"
    )

    for item in result:
        role_map[item["path"]] = FileRoleEntry(
            role=item["role"],
            read_priority=item["read_priority"],
            must_read_for_normalization=item["must_read_for_normalization"],
            reasoning=item["reasoning"]
        )

    # 未出现在LLM输出中的文件默认priority=3
    for path in graph.nodes:
        if path not in role_map:
            role_map[path] = FileRoleEntry(
                role="unknown", read_priority=3,
                must_read_for_normalization=False,
                reasoning="not in LLM output, defaulted to skip"
            )

    return role_map
```

### 输出

`FileRoleMap`（见数据结构定义）

---

## P3 — Skill Package Assembler（纯代码 + 可选LLM fallback）

### 职责

按照P2确定的优先级拼接所有文件内容，生成用于后续所有LLM步骤的单一`merged_doc_text`，并附加边界标记。

### 处理逻辑

```python
def assemble_skill_package(
    graph: FileReferenceGraph,
    role_map: FileRoleMap,
    llm_client=None   # 可选，用于生成摘要
) -> SkillPackage:
    sections = []

    # 按优先级排序：1 → 2 → 3（3直接跳过）
    sorted_files = sorted(
        role_map.items(),
        key=lambda x: x[1].read_priority
    )

    for rel_path, role_entry in sorted_files:
        if role_entry.read_priority == 3:
            continue

        node = graph.nodes.get(rel_path)
        if node is None:
            continue

        full_path = graph.skill_root / rel_path  # 需要传入skill_root

        header = (
            f"=== FILE: {rel_path} | "
            f"role: {role_entry.role} | "
            f"priority: {role_entry.read_priority} ==="
        )
        footer = f"=== END FILE: {rel_path} ==="

        if role_entry.read_priority == 1:
            # 拼入全文
            content = full_path.read_text(errors="replace")

        elif role_entry.read_priority == 2:
            if node.head_lines:
                content = "".join(node.head_lines)
                content += "\n[... remainder omitted, summary-only ...]"
            elif llm_client is not None:
                # LLM fallback：生成2-3句摘要
                content = generate_summary(
                    full_path.read_text(errors="replace"),
                    llm_client
                )
            else:
                # 无LLM且无head_lines：读前20行
                try:
                    with open(full_path) as f:
                        content = "".join(f.readline() for _ in range(20))
                    content += "\n[... remainder omitted ...]"
                except Exception:
                    content = "[unable to read file]"

        sections.append(f"{header}\n{content}\n{footer}\n")

    merged = "\n".join(sections)

    return SkillPackage(
        skill_id=graph.skill_id,
        merged_doc_text=merged,
        capability_profile=graph.capability_profile
    )


def generate_summary(full_text: str, llm_client) -> str:
    """P3的可选LLM摘要生成（极简调用，不使用主pipeline LLM slot）"""
    prompt = (
        "Summarize the following file content in 2-3 sentences. "
        "Focus on what the file does and what it contains. "
        "Output only the summary, no other text.\n\n"
        f"{full_text[:3000]}"  # 截断防止过长
    )
    return llm_client.complete(prompt, max_tokens=120)
```

### 输出

`SkillPackage`（见数据结构定义）

---

## Step 1 — Structure Extraction（LLM）

### 职责

将`merged_doc_text`中的所有内容分类到8个规范section，verbatim复制（不重写），未能归类的内容兜底放入NOTES，不丢弃任何内容。

### 输入

`SkillPackage.merged_doc_text`（完整文本）

### LLM Prompt

```
You are a document structure analyst. Your task is to classify the content of a skill documentation package into exactly 8 canonical sections.

You will receive the full text of a skill package. The text contains multiple files delimited by markers of the form:
  === FILE: <path> | role: <role> | priority: <priority> ===
  ...content...
  === END FILE: <path> ===

Your task:
Read the entire text and assign every piece of content to exactly one of the 8 sections below. Copy content verbatim — do not rewrite, summarize, or paraphrase anything. Every sentence, paragraph, code block, and bullet point from the input must appear in exactly one section of the output.

The 8 sections and what belongs in each:

**INTENT**: The purpose, scope, and goals of the skill. What problem it solves. What it is for. What it is not for. High-level descriptions of what the skill does. Audience descriptions if present.

**WORKFLOW**: Step-by-step procedures. Ordered actions. Branching logic ("if X then Y"). Iteration ("for each"). Numbered or bulleted step lists. Decision trees. Procedural flowcharts described in text.

**CONSTRAINTS**: Normative requirements. Statements using MUST, SHALL, SHOULD, MUST NOT, NEVER, ALWAYS, REQUIRED, FORBIDDEN, or equivalent. Explicit prohibitions. Ordering requirements ("X must happen before Y"). Safety rules. Quality gates.

**TOOLS**: Mentions of specific tools, libraries, scripts, CLIs, APIs, or commands. Installation instructions. Tool invocation examples. Tool configuration. Package names and versions.

**ARTIFACTS**: Inputs and outputs. File formats. Data schemas. Variable declarations. Intermediate products. Typed data contracts. Field specifications. File path patterns.

**EVIDENCE**: Verification requirements. Completion criteria. Validation steps. "Proof" requirements. Exit codes. Required output tokens ("SUCCESS:", "PASS"). Files that must exist as proof of completion. Audit requirements.

**EXAMPLES**: Sample inputs and outputs. Worked examples. Illustrative scenarios. Example file contents. Before/after comparisons.

**NOTES**: Everything that does not clearly belong in any of the above: background context, rationale, caveats, warnings that are not hard constraints, historical notes, design decisions, commentary, tips.

Output format:
Return a single JSON object with exactly these 8 keys: INTENT, WORKFLOW, CONSTRAINTS, TOOLS, ARTIFACTS, EVIDENCE, EXAMPLES, NOTES.

Each key maps to an object:
{
  "text": "<verbatim content, preserve all whitespace, newlines, code blocks>",
  "source": "<pipe-separated list of FILE paths that contributed to this section>",
  "multi": <true if content came from more than one file, false otherwise>
}

Critical rules:
1. **No content may be dropped.** If a piece of content is unclear, put it in NOTES.
2. **No rewriting.** Copy text exactly as it appears in the input. Preserve code formatting, indentation, and punctuation.
3. **No invention.** Do not add content that is not in the input.
4. If a section has no applicable content, set its "text" to "" (empty string), "source" to "", "multi" to false.
5. The FILE boundary markers (=== FILE: ... ===) themselves should NOT appear in any section text.
6. When the same information could belong to multiple sections, prefer the more specific section (e.g., a step with a MUST requirement → put the step text in WORKFLOW, put the constraint text in CONSTRAINTS).

Output valid JSON only. No markdown fences, no explanation text.

Input:
{merged_doc_text}
```

### 后处理（纯代码）

```python
def parse_section_bundle(llm_output: str) -> SectionBundle:
    data = json.loads(llm_output)
    sections = {}
    for key in ["INTENT","WORKFLOW","CONSTRAINTS","TOOLS",
                "ARTIFACTS","EVIDENCE","EXAMPLES","NOTES"]:
        item = data.get(key, {"text":"","source":"","multi":False})
        sections[key] = SectionItem(
            text=item["text"],
            source=item["source"],
            multi=item["multi"]
        )
    return SectionBundle(**sections)
```

### 输出

`SectionBundle`（见数据结构定义）

---

## Step 2A — Clause Extraction + Scoring（LLM）

### 职责

从SectionBundle的所有section文本中识别规范性语句，对每条语句在6个维度评分（0-3），混合语句拆分为子条款。

### 输入

```python
def build_step2a_input(bundle: SectionBundle) -> str:
    """将SectionBundle格式化为LLM输入"""
    sections_text = []
    for section_name in ["INTENT","WORKFLOW","CONSTRAINTS","TOOLS",
                          "ARTIFACTS","EVIDENCE","EXAMPLES","NOTES"]:
        item = getattr(bundle, section_name)
        if item.text.strip():
            sections_text.append(
                f"[SECTION: {section_name} | source: {item.source}]\n"
                f"{item.text}\n"
                f"[END SECTION: {section_name}]"
            )
    return "\n\n".join(sections_text)
```

### LLM Prompt

```
You are a normative clause analyst. Your task is to extract normative clauses from a structured skill document and score each clause on 6 dimensions.

You will receive the text of a skill document divided into labeled sections.

**Part 1 — Clause Identification**

Scan all sections for normative statements. A normative statement is any sentence or clause that:
- Contains explicit modal keywords: MUST, SHALL, SHOULD, MUST NOT, SHALL NOT, SHOULD NOT, NEVER, ALWAYS, REQUIRED, FORBIDDEN, PROHIBITED
- Implies mandatory ordering: "X must exist before Y", "Step A must complete before Step B"
- States a hard prerequisite or gate: "only proceed if", "do not continue unless"
- Describes a non-optional quality requirement with a measurable predicate
- Describes a safety, security, or compliance requirement

Do NOT extract:
- Pure description without normative force ("the tool reads the file")
- Suggestions phrased as options ("you can also try", "optionally")
- Examples that illustrate rather than require

**Part 2 — Scoring**

For each identified clause, score it on 6 dimensions (0–3):

**O — Observability**: Can the clause's predicate be checked from available signals?
- 0: Not checkable (pure preference or vague sentiment)
- 1: Checkable only via human judgment or subjective LLM grading
- 2: Partially checkable with heuristics or approximate metrics
- 3: Reliably checkable with deterministic validators (schema check, exit code, file existence, test pass/fail)

**A — Actionability**: Can the clause be turned into a concrete executable step or gate?
- 0: Not actionable ("be good", "be careful")
- 1: Actionable only as guidance ("consider…", "aim for…")
- 2: Actionable with a defined procedure but requires contextual tooling
- 3: Actionable and can be executed deterministically given the tools described in the document

**F — Formalizability**: Is the meaning crisp enough to formalize?
- 0: Ambiguous or vague; multiple reasonable interpretations
- 1: Somewhat clear but still subjective
- 2: Clear with parameters or thresholds
- 3: Crisp, discrete, well-scoped — a machine could parse it unambiguously

**C — Context dependence**: Does it require facts not present in the document?
- 0: Self-contained
- 1: Needs minor context available in runtime state
- 2: Needs substantial evidence gathering or external information
- 3: Requires human/org policy intent or open-world facts unavailable at runtime

**R — Risk criticality**: How important is enforcement vs. guidance?
- 0: Low stakes; informational
- 1: Mild risk; useful but not critical
- 2: Moderate risk (data writes, spending, compliance)
- 3: High risk (security, data leakage, legal, irreversible production changes)

**V — Verifiability**: Can you prove the clause was satisfied after execution?
- 0: Not verifiable
- 1: Verifiable by human review only
- 2: Verifiable by metrics, heuristics, or evidence artifacts
- 3: Verifiable by deterministic checks + logs

**Part 3 — Split Rule**

If a single sentence contains BOTH an enforceable predicate AND a subjective quality requirement, split it into sub-clauses. Example:
"The output MUST contain all required fields and be well-written." →
  sub-clause 1: "The output MUST contain all required fields." (high O/F/V)
  sub-clause 2: "The output MUST be well-written." (low O/F)

Assign a parent_clause_id to all sub-clauses. The parent clause should also appear in the output with split=true.

**Output format**

Return a JSON array. Each element:
{
  "clause_id": "C001",              // Sequential: C001, C002, ...
  "original_text": "<verbatim>",    // Exact text from the document
  "source_section": "CONSTRAINTS",  // Which section it came from
  "source_file": "<rel_path>",      // From the section's source field
  "scores": {"O": 0, "A": 0, "F": 0, "C": 0, "R": 0, "V": 0},
  "is_normative": true,
  "split": false,                   // true if this is a sub-clause
  "parent_clause_id": null,         // clause_id of parent if split=true
  "confidence": 0.9                 // your confidence in the scores, 0.0-1.0
}

Rules:
- clause_id must be globally unique across all clauses in the output
- Sub-clauses get their own clause_ids (e.g. C003a, C003b) with parent_clause_id pointing to the parent
- original_text must be verbatim from the input — never rephrase
- If a clause appears in multiple sections with identical text, include it once and use the section where it most naturally belongs
- Output valid JSON array only. No markdown, no explanation.

Input:
{section_bundle_text}
```

### 输出

`list[RawClause]`（见数据结构定义）

---

## Step 2B — Classification（纯代码）

### 职责

基于Step 2A的评分，用决策表将每个RawClause分类为HARD/MEDIUM/SOFT/NON，应用风险升级和capability降级规则。

### 处理逻辑

```python
def classify_clauses(
    raw_clauses: list[RawClause],
    capability_profile: CapabilityProfile
) -> list[ClassifiedClause]:
    results = []

    # split父条款：如果一个clause有子条款，则父条款本身不单独分类
    # 子条款替代父条款参与分类
    has_children = {
        c.parent_clause_id
        for c in raw_clauses
        if c.parent_clause_id is not None
    }

    for clause in raw_clauses:
        # 父条款被子条款替换，不单独分类
        if clause.clause_id in has_children:
            # 仍然加入输出，但标记为已被拆分
            results.append(ClassifiedClause(
                **asdict(clause),
                classification="COMPILABLE_SOFT",  # 占位
                S_det=0, S_proc=0,
                confidence=clause.confidence,
                needs_review=False,
                risk_override=False,
                downgraded=False,
                enforcement_backends=[],
                # 标记：此条款已被子条款替代，不应被pipeline消费
                _replaced_by_children=True
            ))
            continue

        s = clause.scores
        S_det = min(s.O, s.F, s.V)
        S_proc = min(s.A, s.V)

        # ── 基础分类 ──────────────────────────────────
        if S_det >= 3 and s.A >= 2 and s.C <= 2:
            classification = "COMPILABLE_HARD"
        elif (
            (S_det == 2 and s.A >= 2) or
            (S_det >= 3 and s.C == 3)
        ):
            classification = "COMPILABLE_MEDIUM"
        elif S_det <= 1 and s.A >= 1:
            classification = "COMPILABLE_SOFT"
        elif s.A == 0 or (s.O == 0 and s.F == 0):
            classification = "NON_COMPILABLE"
        else:
            classification = "COMPILABLE_SOFT"

        # ── 风险升级规则 ──────────────────────────────
        risk_override = False
        if s.R == 3 and classification == "COMPILABLE_SOFT":
            classification = "COMPILABLE_MEDIUM"
            risk_override = True

        # ── Capability降级规则 ────────────────────────
        downgraded = False
        if classification == "COMPILABLE_HARD":
            required_effects = infer_required_effects(clause.original_text)
            if not all(
                effect_available(e, capability_profile)
                for e in required_effects
            ):
                classification = "COMPILABLE_MEDIUM"
                downgraded = True

        # ── needs_review判断 ──────────────────────────
        needs_review = (
            clause.confidence < 0.7 or
            downgraded or
            (risk_override and classification == "COMPILABLE_MEDIUM")
        )

        # ── enforcement_backends映射 ──────────────────
        backends = []
        if classification == "COMPILABLE_HARD":
            if S_det >= 3 and s.V >= 3:
                backends.append("json_schema")
            if "exist" in clause.original_text.lower() or \
               "output" in clause.original_text.lower():
                backends.append("file_existence_check")
            if any(kw in clause.original_text.lower()
                   for kw in ["exit code", "return code", "success"]):
                backends.append("exit_code_check")

        results.append(ClassifiedClause(
            **asdict(clause),
            classification=classification,
            S_det=S_det, S_proc=S_proc,
            confidence=clause.confidence,
            needs_review=needs_review,
            risk_override=risk_override,
            downgraded=downgraded,
            enforcement_backends=backends
        ))

    return results


def infer_required_effects(clause_text: str) -> list[str]:
    """从clause文本中推断执行该约束所需的runtime effects"""
    text = clause_text.lower()
    effects = []
    if any(kw in text for kw in ["api", "http", "request", "endpoint", "url"]):
        effects.append("NETWORK")
    if any(kw in text for kw in ["file", "write", "create", "save", "output"]):
        effects.append("DISK_WRITE")
    if any(kw in text for kw in ["script", ".py", ".sh", "run", "execute"]):
        effects.append("EXEC")
    return effects


def effect_available(effect: str, profile: CapabilityProfile) -> bool:
    """检查capability_profile中是否支持该effect"""
    if effect == "NETWORK":
        return (
            "network" in profile.available_tools or
            profile.runtime_env in ["cloud", "mcp"]
        )
    if effect == "DISK_WRITE":
        return True  # 本地运行默认可写磁盘
    if effect == "EXEC":
        return len(profile.local_scripts) > 0
    return True  # 未知effect保守地认为可用
```

### 输出

`list[ClassifiedClause]`（见数据结构定义）

---

## Step 3 — Structured Entity and Step Extraction（LLM）

### 职责

从SectionBundle和ClassifiedClauses中提取数据实体（→ SPL VARIABLES/FILES）、工作流步骤（→ SPL WORKER MAIN_FLOW）、交互要求（→ SPL INPUT commands）以及成功标准。

### 输入

```python
def build_step3_input(
    bundle: SectionBundle,
    classified_clauses: list[ClassifiedClause]
) -> str:
    # 过滤：只取HARD+MEDIUM clauses作为步骤上下文
    gate_clauses = [
        c for c in classified_clauses
        if c.classification in ("COMPILABLE_HARD", "COMPILABLE_MEDIUM")
        and not getattr(c, '_replaced_by_children', False)
    ]
    # NON_COMPILABLE clauses作为interaction requirements来源
    non_clauses = [
        c for c in classified_clauses
        if c.classification == "NON_COMPILABLE"
        and not getattr(c, '_replaced_by_children', False)
    ]

    return json.dumps({
        "WORKFLOW": bundle.WORKFLOW.text,
        "TOOLS": bundle.TOOLS.text,
        "ARTIFACTS": bundle.ARTIFACTS.text,
        "EVIDENCE": bundle.EVIDENCE.text,
        "EXAMPLES": bundle.EXAMPLES.text,
        "gate_clauses": [
            {
                "clause_id": c.clause_id,
                "text": c.original_text,
                "classification": c.classification,
                "source_section": c.source_section
            }
            for c in gate_clauses
        ],
        "non_compilable_clauses": [
            {
                "clause_id": c.clause_id,
                "text": c.original_text
            }
            for c in non_clauses
        ]
    }, ensure_ascii=False, indent=2)
```

### LLM Prompt

```
You are a software interface analyst. Your task is to extract structured entities, workflow steps, and interaction requirements from a skill specification document.

You will receive a JSON object with these fields:
- `WORKFLOW`: the workflow section of the skill (procedural steps)
- `TOOLS`: tool mentions in the skill
- `ARTIFACTS`: artifact/data descriptions in the skill
- `EVIDENCE`: verification and validation requirements
- `EXAMPLES`: example inputs/outputs
- `gate_clauses`: normative clauses classified as HARD or MEDIUM
- `non_compilable_clauses`: clauses that require human input to proceed

Your task is to produce a single JSON object with 5 fields: `entities`, `workflow_steps`, `interaction_requirements`, `success_criteria`, `needs_review_items`.

---

**Field 1: entities**

Extract all data entities mentioned in ARTIFACTS, WORKFLOW, and EXAMPLES. An entity is anything that:
- Is passed between steps as input or output
- Is written to or read from disk (file artifact)
- Is held in memory as a named data structure
- Is referenced by name in multiple steps

For each entity:
{
  "entity_id": "<snake_case name>",
  "kind": "Artifact" | "Run" | "Evidence" | "Record" | "Config",
  // Artifact = disk file; Run = execution record; Evidence = proof artifact;
  // Record = structured in-memory data; Config = read-only configuration value
  "type_name": "<natural language type description, e.g. 'JSON array of field descriptors'>",
  "schema_notes": "<description of fields/structure if mentioned in source>",
  "is_file": true | false,
  "file_path": "<exact path from source, or '< >' if not specified, or null if not a file>",
  "provenance": {
    "source": "EXPLICIT" | "ASSUMED" | "LOW_CONFIDENCE",
    // EXPLICIT: entity is named and described in the source text
    // ASSUMED: entity is implied by context but not named
    // LOW_CONFIDENCE: entity's structure is unclear or inferred
    "source_text": "<verbatim quote from source that describes this entity>",
    "source_file": "<section name: ARTIFACTS | WORKFLOW | EXAMPLES>"
  }
}

Rules for entities:
- Only use EXPLICIT when the entity is named AND its type/structure is described in the source
- Use ASSUMED when the entity is necessary for the workflow but only implied
- Use LOW_CONFIDENCE when you can identify the entity but its schema is unclear
- ASSUMED and LOW_CONFIDENCE entities must use "< >" as file_path if is_file=true

---

**Field 2: workflow_steps**

Extract the ordered execution steps from WORKFLOW. Each step should be described at the level of one meaningful action (not sub-actions within a step).

For each step:
{
  "step_id": "S01",   // Sequential: S01, S02, ...
  "description": "<SPL-ready natural language description of what this step does>",
  "prerequisites": ["<entity_id>", ...],   // entities that must exist before this step
  "produces": ["<entity_id>", ...],        // entities this step creates or updates
  "effects": ["DISK_WRITE" | "DISK_READ" | "NETWORK" | "LLM_CALL" | "EXEC" | "DISPLAY" | "INPUT"],
  "is_validation_gate": true | false,
  // true only if: (a) the step is from the EVIDENCE section, AND
  //              (b) the step has a clear pass/fail outcome described in source
  "tool_hint": "<tool name from TOOLS section relevant to this step, or null>",
  "provenance": {
    "source": "EXPLICIT" | "ASSUMED" | "LOW_CONFIDENCE",
    "source_text": "<verbatim quote from WORKFLOW or EVIDENCE>",
    "source_file": "WORKFLOW" | "EVIDENCE"
  }
}

Rules for workflow_steps:
- Preserve the original ordering from WORKFLOW
- is_validation_gate=true only for steps explicitly in EVIDENCE with a checkable pass/fail signal
- tool_hint must be a name that appears verbatim in the TOOLS section
- "LLM_CALL" effect: use when the step requires semantic judgment or generation
- Do not invent steps. Every step must have a verbatim source_text quote.

---

**Field 3: interaction_requirements**

For each clause in `non_compilable_clauses`, determine if it requires the agent to ask the user for input or confirmation before proceeding.

For each interaction requirement:
{
  "req_id": "IR01",
  "description": "<what the agent needs from the user>",
  "source_clause_id": "<clause_id from non_compilable_clauses>",
  "input_type": "confirmation" | "file_upload" | "text" | "selection" | "unknown"
}

Only include a non_compilable_clause as an interaction requirement if it clearly implies a user decision point. Clauses that are simply subjective guidance (not requiring user input) should be omitted.

---

**Field 4: success_criteria**

Extract the overall completion conditions from EVIDENCE and WORKFLOW.

{
  "description": "<natural language description of what 'done' means for this skill>",
  "deterministic": true | false,  // true if success can be verified programmatically
  "source_text": "<verbatim quote from EVIDENCE or WORKFLOW>",
  "source_file": "EVIDENCE" | "WORKFLOW"
}

If no explicit success criteria is stated, set deterministic=false and derive a reasonable description from the WORKFLOW's final step, marking it LOW_CONFIDENCE.

---

**Field 5: needs_review_items**

List any ambiguities, conflicts, or unclear mappings you encountered during extraction.

[
  {
    "item": "<entity_id or step_id or 'global'>",
    "reason": "<why this needs review>",
    "question": "<specific question a human reviewer should answer>"
  }
]

---

Output valid JSON only. No markdown, no explanation text.

Input:
{step3_input_json}
```

### 后处理（纯代码）

```python
def parse_structured_spec(llm_output: str) -> StructuredSpec:
    data = json.loads(llm_output)

    entities = [Entity(**e) for e in data["entities"]]
    steps = [WorkflowStep(**s) for s in data["workflow_steps"]]
    interactions = [
        InteractionRequirement(**i)
        for i in data["interaction_requirements"]
    ]

    # 应用置信度降级规则：
    # ASSUMED/LOW_CONFIDENCE的entity，如果对应clause是HARD，
    # 在后续Step 4中必须降为MEDIUM（此处标记）
    for entity in entities:
        if entity.provenance.source in ("ASSUMED", "LOW_CONFIDENCE"):
            entity._max_classification = "COMPILABLE_MEDIUM"

    return StructuredSpec(
        entities=entities,
        workflow_steps=steps,
        interaction_requirements=interactions,
        success_criteria=data["success_criteria"],
        needs_review_items=data.get("needs_review_items", [])
    )
```

### 输出

`StructuredSpec`（见数据结构定义）

---

## Step 4 — SPL Emission（5次LLM调用）

Step 4的完整设计见 `/mnt/skills/user/spl-emitter/SKILL.md`，其中包含：

- Round 1（4路并行）：S4A（PERSONA/AUDIENCE/CONCEPTS）、S4B（DEFINE_CONSTRAINTS）、S4C（DEFINE_VARIABLES + DEFINE_FILES）、S4D（DEFINE_GUARDRAIL + DEFINE_APIS）
- Symbol Table提取（纯代码regex）：从Round 1输出提取所有已定义名称
- Round 2（S4E）：DEFINE_WORKER（MAIN_FLOW / ALTERNATIVE_FLOW / EXCEPTION_FLOW / EXAMPLES）

### Step 4的输入汇总

```python
@dataclass
class Step4Input:
    # Round 1并行输入
    s4a_input: dict  # bundle[INTENT] + bundle[NOTES]
    s4b_input: dict  # classified_clauses（HARD + SOFT only）
    s4c_input: dict  # structured_spec.entities
    s4d_input: dict  # validation_steps + network_steps

    # Round 2输入（需等待Round 1完成后提取Symbol Table）
    s4e_input: dict  # main_steps + bundle[WORKFLOW] + interaction_requirements
                     # + MEDIUM_clauses + validation_steps + bundle[EXAMPLES]
                     # + symbol_table（来自Round 1正则提取）

def build_step4_inputs(
    bundle: SectionBundle,
    classified_clauses: list[ClassifiedClause],
    spec: StructuredSpec
) -> Step4Input:

    # 过滤各类clauses（排除父条款占位符）
    active = [
        c for c in classified_clauses
        if not getattr(c, '_replaced_by_children', False)
    ]
    hard_soft = [
        c for c in active
        if c.classification in ("COMPILABLE_HARD", "COMPILABLE_SOFT")
    ]
    medium = [
        c for c in active
        if c.classification == "COMPILABLE_MEDIUM"
    ]
    validation_steps = [
        s for s in spec.workflow_steps
        if s.is_validation_gate
    ]
    network_steps = [
        s for s in spec.workflow_steps
        if "NETWORK" in s.effects and not s.is_validation_gate
    ]
    main_steps = [
        s for s in spec.workflow_steps
        if not s.is_validation_gate and "NETWORK" not in s.effects
    ]

    return Step4Input(
        s4a_input={
            "INTENT": bundle.INTENT.text,
            "NOTES": bundle.NOTES.text
        },
        s4b_input={
            "clauses": [asdict(c) for c in hard_soft]
        },
        s4c_input={
            "entities": [asdict(e) for e in spec.entities]
        },
        s4d_input={
            "validation_steps": [asdict(s) for s in validation_steps],
            "network_steps": [asdict(s) for s in network_steps]
        },
        s4e_input={
            "main_steps": [asdict(s) for s in main_steps],
            "workflow_text": bundle.WORKFLOW.text,
            "interaction_requirements": [asdict(i) for i in spec.interaction_requirements],
            "medium_clauses": [asdict(c) for c in medium],
            "validation_steps": [asdict(s) for s in validation_steps],
            "examples_text": bundle.EXAMPLES.text,
            "success_criteria": spec.success_criteria,
            # symbol_table在Round 1完成后填入
        }
    )
```

### Symbol Table提取（纯代码）

```python
import re

def extract_symbol_table(
    s4b_output: str,
    s4c_output: str,
    s4d_output: str
) -> dict:
    """从Round 1的SPL文本输出中提取所有已定义名称"""
    all_text = s4b_output + "\n" + s4c_output + "\n" + s4d_output

    return {
        "constraint_aspects": re.findall(
            r"^\s*([A-Z][A-Za-z_]+)\s*:", all_text, re.MULTILINE
        ),
        "variables": re.findall(
            r"^\s*(?:READONLY\s+)?([a-z][a-z0-9_]+)\s*:", all_text, re.MULTILINE
        ),
        "files": re.findall(
            r"^\s*([a-z][a-z0-9_]+)\s+[<\w/]", all_text, re.MULTILINE
        ),
        "guardrails": re.findall(
            r"\[DEFINE_GUARDRAIL[:\s]+[\"']?([A-Za-z_]+)[\"']?", all_text
        ),
        "apis": re.findall(
            r"^\s*([A-Z][A-Za-z0-9_]+)\s*<", all_text, re.MULTILINE
        ),
    }
```

---

## 数据流检查表

执行前可用此检查表验证各步骤输入是否完整：

| 步骤 | 必需输入 | 来源 |
|------|---------|------|
| P1 | `skill_root: Path`（含SKILL.md） | 调用方 |
| P2 | `FileReferenceGraph` | P1 |
| P3 | `FileReferenceGraph` + `FileRoleMap` | P1 + P2 |
| Step 1 | `SkillPackage.merged_doc_text` | P3 |
| Step 2A | `SectionBundle`（全部8 sections） | Step 1 |
| Step 2B | `list[RawClause]` + `CapabilityProfile` | Step 2A + P1（内嵌于P3） |
| Step 3 | `SectionBundle` + `list[ClassifiedClause]` | Step 1 + Step 2B |
| Step 4 Round 1 | `SectionBundle` + `list[ClassifiedClause]` + `StructuredSpec` | Step 1+2B+3 |
| Step 4 Round 2 | Round 1输出 + `symbol_table` | Step 4 Round 1 |

---

## 错误处理约定

| 错误类型 | 处理方式 |
|---------|---------|
| SKILL.md缺失 | P1抛出`SkillRootError`，终止pipeline |
| P2 LLM输出非法JSON | 回退：所有非SKILL.md文件降级为priority=2 |
| Step 1 section全空 | 允许，SectionBundle中该section的text="" |
| Step 2A无任何clause | 允许，返回空list；Step 4不生成CONSTRAINTS块 |
| Step 3 LLM输出缺字段 | 用空列表填充，全部标记needs_review=True |
| Step 4任一Round失败 | 对应SPL块标记`"""EMISSION_FAILED: <reason>"""`，不中止pipeline |

---

## 快速参考：各SPL块的完整来源链

```
DEFINE_PERSONA    ← Step1[INTENT]  →  S4A
DEFINE_AUDIENCE   ← Step1[INTENT / NOTES]  →  S4A
DEFINE_CONCEPTS   ← Step1[INTENT + NOTES]（术语定义）  →  S4A
DEFINE_CONSTRAINTS
  HARD clauses    ← Step2B[COMPILABLE_HARD]  →  S4B（带LOG）
  SOFT clauses    ← Step2B[COMPILABLE_SOFT]  →  S4B（无LOG）
DEFINE_VARIABLES  ← Step3[entities where kind != Artifact]  →  S4C
DEFINE_FILES      ← Step3[entities where kind == Artifact]  →  S4C
DEFINE_APIS       ← Step3[network_steps]（推断Schema）  →  S4D
DEFINE_GUARDRAIL  ← Step3[validation_steps where is_validation_gate=True]  →  S4D
DEFINE_WORKER
  MAIN_FLOW       ← Step3[main_steps] + Step1[WORKFLOW]分支/循环逻辑  →  S4E
  ALTERNATIVE_FLOW← Step2B[COMPILABLE_MEDIUM]  →  S4E
  EXCEPTION_FLOW  ← Step3[validation_steps]（失败路径）  →  S4E
  [INPUT/DISPLAY] ← Step3[interaction_requirements]（NON_COMPILABLE来源）  →  S4E
  [EXAMPLES]      ← Step1[EXAMPLES] + Step3[success_criteria]  →  S4E
```
