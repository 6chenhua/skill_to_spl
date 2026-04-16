# HITL Clarification Module

Human-in-the-loop clarification module for detecting and resolving ambiguous requirements in the simplified pipeline.

## Overview

This module adds interactive clarification capability to the `simplified_pipeline`, enabling:

1. **Automatic ambiguity detection** in requirements using hybrid (rule-based + LLM) approach
2. **Business-domain question generation** - users see business questions, not SPL jargon
3. **Interactive user feedback** via console or programmatic interface
4. **Clarified data integration** back into the pipeline for improved SPL generation

## Architecture

```
simplified_pipeline/
├── orchestrator.py          # Modified: HITL integration after Step 1
├── models.py                # Modified: PipelineResult with clarification_context
└── clarification/
    ├── __init__.py          # Module exports
    ├── models.py            # Data models
    ├── detector.py          # Ambiguity detection engine
    ├── questions.py         # Question generation system
    ├── ui.py                # User interaction interfaces
    ├── manager.py           # State orchestrator
    ├── prompts.py           # LLM prompts
    ├── test_detector.py     # Detector tests
    ├── test_questions.py    # Question generator tests
    └── test_ui.py           # UI tests
```

## Quick Start

### Basic Usage (Disabled by Default)

```python
from simplified_pipeline import run_simplified_pipeline

# Run without clarification (default)
result = run_simplified_pipeline(
    merged_doc_text="Your skill documentation...",
    skill_id="my_skill",
)
```

### Enable HITL Clarification

```python
from simplified_pipeline import run_simplified_pipeline

# Run with clarification enabled
result = run_simplified_pipeline(
    merged_doc_text="Your skill documentation...",
    skill_id="my_skill",
    enable_clarification=True,
    clarification_sensitivity="medium",  # "low", "medium", "high"
)

# Check if clarification was used
if result.clarification_context:
    print(f"Clarified {len(result.clarification_context.questions)} ambiguities")
```

### Using PipelineConfig

```python
from simplified_pipeline.orchestrator import run_pipeline, PipelineConfig
from simplified_pipeline.llm_client import LLMConfig

config = PipelineConfig(
    merged_doc_text="Your skill documentation...",
    skill_id="my_skill",
    output_dir="output/my_skill",
    llm_config=LLMConfig(model="gpt-4o"),
    save_checkpoints=True,
    # HITL Configuration
    enable_clarification=True,
    clarification_sensitivity="medium",
    clarification_max_iterations=5,
)

result = run_pipeline(config)
```

## Ambiguity Detection

### Detection Types

| Type | Description | Example |
|------|-------------|---------|
| `LEXICAL` | Word with multiple meanings | "bank", "green", "light" |
| `SYNTACTIC` | Multiple parse interpretations | "The Tibetan history teacher" |
| `SEMANTIC` | Scope/quantifier ambiguity | "All users need a license" |
| `PRAGMATIC` | Vague context-dependent terms | "fast", "sufficient", "appropriate" |
| `QUANTIFIER` | Vague quantity words | "many", "few", "some", "most" |
| `OPTIONALITY` | Uncertain requirement strength | "may", "might", "optionally" |
| `WEAK_WORD` | Subjective criteria | "appropriate", "suitable", "adequate" |
| `REFERENCE` | Unclear pronoun antecedents | "it", "they", "this" |
| `NEGATION` | Double/unclear negation | "not uncommon", "not impossible" |

### Sensitivity Levels

| Level | Defect Density Threshold | Confidence Threshold | Use Case |
|-------|-------------------------|---------------------|----------|
| `low` | 0.25 | 0.5 | Fewer interruptions, high-confidence ambiguities only |
| `medium` | 0.15 | 0.7 | Balanced detection (recommended) |
| `high` | 0.10 | 0.8 | More thorough, catches subtle ambiguities |

## Question Generation

### Template-Based Generation

Common ambiguity patterns use predefined templates:

```python
# Quantifier ambiguity
"'many' is a vague quantity. Please specify the approximate range:"
Options: ["10-50", "50-500", "500+", "Other: ____"]

# Optionality ambiguity
"The requirement uses 'may' which suggests optionality. Is this feature required or optional?"
Options: ["Required for all cases", "Optional - depends on conditions", "Recommended but not mandatory", "Other: ____"]

# Weak word ambiguity
"'fast' is subjective. What would be considered 'fast' in this context?"
Options: ["Under 1 second", "1-5 seconds", "Under 1 minute", "Other: ____"]
```

### LLM-Based Generation

Complex or novel ambiguity types use LLM for question generation:

```python
from clarification import QuestionGenerator

generator = QuestionGenerator(llm_client=client)
result = generator.generate_questions(markers)

for question in result.questions:
    print(f"Q: {question.question_text}")
    for opt in question.options:
        print(f"  - {opt}")
```

## User Interface

### Console Interface

```python
from clarification.ui import ConsoleClarificationUI

ui = ConsoleClarificationUI()

# Present question and collect response
ui.present_question(question)
response = ui.collect_response(question)

# Show summary at the end
ui.present_summary(context)
```

### Mock Interface (Testing)

```python
from clarification.ui import MockClarificationUI

# Predefined responses for automated testing
ui = MockClarificationUI({
    "q_0001": "10-50",  # Select first option
    "q_0002": {"selected_option": "CUSTOM", "custom_answer": "My custom answer"},
})

# Run clarification with mock
manager = ClarificationManager(detector, question_gen, ui)
context = manager.run_clarification(bundle)
```

### Custom Interface

Implement the `ClarificationUI` protocol:

```python
from clarification.ui import ClarificationUI, ClarificationQuestion, UserResponse

class WebClarificationUI(ClarificationUI):
    def present_question(self, question: ClarificationQuestion) -> None:
        # Send question to web frontend
        pass
    
    def collect_response(self, question: ClarificationQuestion) -> UserResponse:
        # Wait for web response
        pass
    
    def present_summary(self, context) -> None:
        # Display summary on web
        pass
    
    def confirm_proceed(self, message: str) -> bool:
        # Get user confirmation
        pass
```

## Pipeline Integration

The clarification module integrates into the pipeline after Step 1:

```
Input: merged_doc_text
    ↓
Step 1: Structure Extraction → SectionBundle
    ↓
[HITL: Ambiguity Detection]
    ↓ (if needed)
[HITL: Question Generation → User Interaction → Answer Collection]
    ↓ (clarified SectionBundle)
Step 3A: Variable Extraction
    ↓
Step 3B: Workflow Analysis
    ↓
Step 4: SPL Emission
    ↓
Output: SPL Specification
```

## Data Models

### AmbiguityMarker

```python
@dataclass
class AmbiguityMarker:
    source_text: str           # Exact text causing ambiguity
    ambiguity_type: AmbiguityType
    severity: float            # 0.0-1.0
    source: AmbiguitySource    # RULE_BASED | LLM_BASED | HYBRID
    section_name: str          # INTENT | WORKFLOW | CONSTRAINTS | EXAMPLES | NOTES
    source_item_index: int
    explanation: str
    suggestions: list[str]
    confidence: float          # 0.0-1.0
```

### ClarificationQuestion

```python
@dataclass
class ClarificationQuestion:
    question_id: str
    ambiguity_marker_id: str
    question_text: str         # Business-domain question (no SPL jargon)
    options: list[str]         # Multiple choice options
    allow_other: bool          # Include "Other: ____" option
    context_hint: str          # Why this matters
    priority: QuestionPriority # CRITICAL | HIGH | MEDIUM | LOW
```

### ClarificationContext

```python
@dataclass
class ClarificationContext:
    session_id: str
    markers: list[AmbiguityMarker]
    questions: list[ClarificationQuestion]
    responses: list[UserResponse]
    iteration: int
    max_iterations: int
    status: ClarificationStatus  # PENDING | IN_PROGRESS | COMPLETED | ABANDONED
```

## Checkpoint System

Clarification state can be saved and restored:

```python
from clarification.manager import ClarificationManager

manager = ClarificationManager(detector, question_gen, ui)

# Save checkpoint
manager.save_checkpoint(context, "output/clarification_session.json")

# Load and resume
context = manager.load_checkpoint("output/clarification_session.json")
context = manager.run_from_checkpoint(bundle, "output/clarification_session.json")
```

## Testing

Run tests with pytest:

```bash
# Run all clarification tests
pytest simplified_pipeline/clarification/test_*.py -v

# Run specific test file
pytest simplified_pipeline/clarification/test_detector.py -v

# Run with coverage
pytest simplified_pipeline/clarification/ --cov=clarification --cov-report=html
```

## Key Principles

### 1. SPL is Hidden from Users

Users never see:
- SPL block markers (`[DEFINE_VARIABLES:]`, `[END_VARIABLES]`)
- Variable identifiers (`var_id`, `type_name`)
- Action types (`LLM_TASK`, `FILE_READ`)
- Reference tags (`<REF>`, `</REF>`)

Questions are always in business language:
- "How many users should this support?" (not "What is the value of `user_count`?")
- "What response time is acceptable?" (not "Define `response_time` threshold")

### 2. One Question at a Time

The system presents questions sequentially, not in bulk:
- User focuses on one decision at a time
- Questions are ordered by priority
- Iteration limit prevents endless loops

### 3. Graceful Degradation

- If clarification is disabled, pipeline runs normally
- If no ambiguities detected, no user interaction
- If max iterations reached, session completes with partial results
- Checkpoints enable resumption

## Research References

This implementation draws from:

1. **AmbiSQL** (SIGMOD 2026) - Interactive ambiguity detection for NL2SQL
2. **CLAM Framework** (2022) - Detect → Generate Question → Respond
3. **QuARS Tool** (SEI/CMU) - Linguistic defect detection patterns
4. **Rao & Daumé III** (NAACL 2019) - Utility-based question generation
5. **ClarifyGPT** (ACM SIGPLAN 2024) - Requirements clarification for code generation

## License

Proprietary. See project LICENSE for details.
