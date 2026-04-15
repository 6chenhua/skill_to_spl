"""
Prompts for question generation in the clarification module.

These prompts are used by the LLM to generate business-domain
clarification questions from detected ambiguities.
"""

from __future__ import annotations


# ═════════════════════════════════════════════════════════════════════════════
# QUESTION GENERATION PROMPT
# ═════════════════════════════════════════════════════════════════════════════

QUESTION_GENERATION_SYSTEM = """\
You are generating clarification questions for business users.

CRITICAL RULES:
1. Users are NOT technical - do NOT use SPL, SQL, or programming terminology
2. Translate all technical ambiguities into business-domain questions
3. Questions should be clear and actionable for non-technical stakeholders
4. Always provide multiple choice options with an "Other" option

## What to AVOID:
- Technical jargon: "variable", "type", "schema", "workflow step"
- SPL terms: "DEFINE_VARIABLES", "MAIN_FLOW", "COMMAND", "REF"
- Programming concepts: "API", "function", "parameter", "return value"
- Internal implementation details

## What to USE:
- Business language: "information", "data", "process", "requirement"
- User-focused terms: "when", "how many", "what type", "which option"
- Concrete examples: "within 1 second", "10-50 items", "daily"
- Context that matters to users

## Question Structure:
1. Clear, simple question text (one sentence)
2. 3-4 specific multiple choice options
3. Brief context hint explaining why this matters
"""

QUESTION_GENERATION_USER = """\
## Detected Ambiguity:
- Type: {ambiguity_type}
- Text: "{source_text}"
- Section: {section}
- Description: {description}
- Term: "{term}"

## Task:
Generate a clear, business-focused clarification question.

Output as JSON:
{{
    "question_text": "A clear question in business terms (no technical jargon)",
    "options": ["Option A", "Option B", "Option C", "Other: ____"],
    "context_hint": "Why this matters for the business user"
}}

Remember: The user is a business stakeholder, not a developer.
"""


def render_question_generation_prompt(
    ambiguity_type: str,
    source_text: str,
    section: str,
    description: str,
    term: str,
) -> str:
    """
    Render the question generation prompt with the given parameters.
    
    Args:
        ambiguity_type: Type of ambiguity detected
        source_text: The original text containing the ambiguity
        section: Which section this was found in
        description: Description of the ambiguity
        term: The specific term that is ambiguous
        
    Returns:
        Formatted prompt string
    """
    return QUESTION_GENERATION_USER.format(
        ambiguity_type=ambiguity_type,
        source_text=source_text,
        section=section,
        description=description,
        term=term,
    )


# ═════════════════════════════════════════════════════════════════════════════
# BATCH QUESTION GENERATION PROMPT
# ═════════════════════════════════════════════════════════════════════════════

BATCH_QUESTION_GENERATION_SYSTEM = """\
You are generating multiple clarification questions for business users.

CRITICAL RULES:
1. Users are NOT technical - do NOT use SPL, SQL, or programming terminology
2. Each question must be independent and self-contained
3. Questions should be ordered by importance (most critical first)
4. Provide clear, actionable options for each question

## Output Format:
Return a JSON array of questions, each with:
- question_text: Clear business question
- options: 3-4 specific choices plus "Other: ____"
- context_hint: Why this matters
- priority: "critical", "high", "medium", or "low"
"""

BATCH_QUESTION_GENERATION_USER = """\
## Ambiguity Markers:
{markers_json}

## Task:
Generate clarification questions for each ambiguity.

Output as JSON array:
[
    {{
        "ambiguity_index": 0,
        "question_text": "...",
        "options": ["...", "...", "..."],
        "context_hint": "...",
        "priority": "high"
    }},
    ...
]

Remember: Business language only, no technical jargon.
"""


def render_batch_question_generation_prompt(
    markers_json: str,
) -> str:
    """
    Render the batch question generation prompt.
    
    Args:
        markers_json: JSON string of ambiguity markers
        
    Returns:
        Formatted prompt string
    """
    return BATCH_QUESTION_GENERATION_USER.format(markers_json=markers_json)


# ═════════════════════════════════════════════════════════════════════════════
# QUESTION REFINEMENT PROMPT
# ═════════════════════════════════════════════════════════════════════════════

QUESTION_REFINEMENT_SYSTEM = """\
You are refining clarification questions to ensure they are:
1. Clear and unambiguous for business users
2. Free of technical jargon
3. Actionable with specific options
4. Properly prioritized

Review the question and suggest improvements if needed.
"""

QUESTION_REFINEMENT_USER = """\
## Original Question:
{question_text}

## Options:
{options}

## Context Hint:
{context_hint}

## Original Ambiguity:
- Type: {ambiguity_type}
- Source: "{source_text}"

## Task:
Review and refine this question. If it's already good, return it unchanged.
If it contains technical jargon or could be clearer, provide an improved version.

Output as JSON:
{{
    "question_text": "Refined question text",
    "options": ["Refined option 1", "Refined option 2", ...],
    "context_hint": "Refined context hint",
    "changes_made": true/false,
    "change_description": "What was changed and why" (if changes_made is true)
}}
"""


def render_question_refinement_prompt(
    question_text: str,
    options: list[str],
    context_hint: str,
    ambiguity_type: str,
    source_text: str,
) -> str:
    """
    Render the question refinement prompt.
    
    Args:
        question_text: The original question text
        options: List of options
        context_hint: The context hint
        ambiguity_type: Type of ambiguity
        source_text: Original ambiguous text
        
    Returns:
        Formatted prompt string
    """
    return QUESTION_REFINEMENT_USER.format(
        question_text=question_text,
        options="\n".join(f"- {opt}" for opt in options),
        context_hint=context_hint,
        ambiguity_type=ambiguity_type,
        source_text=source_text,
    )


# ═════════════════════════════════════════════════════════════════════════════
# ANSWER PROCESSING PROMPT
# ═════════════════════════════════════════════════════════════════════════════

ANSWER_PROCESSING_SYSTEM = """\
You are processing user answers to clarification questions.

Your task is to:
1. Validate that the answer addresses the question
2. Extract the key information from the answer
3. Format it for use in requirement refinement

Output structured data that can be used to update the requirements.
"""

ANSWER_PROCESSING_USER = """\
## Question:
{question_text}

## Options Provided:
{options}

## User's Answer:
{user_answer}

## Task:
Process this answer and extract the key clarification.

Output as JSON:
{{
    "answer_type": "choice" | "text" | "clarification",
    "selected_option": "The option chosen (if applicable)",
    "free_text": "Additional clarification text (if applicable)",
    "key_information": "The essential information extracted",
    "confidence": 0.0-1.0,
    "needs_followup": true/false,
    "followup_question": "If needs_followup is true, what to ask"
}}
"""


def render_answer_processing_prompt(
    question_text: str,
    options: list[str],
    user_answer: str,
) -> str:
    """
    Render the answer processing prompt.
    
    Args:
        question_text: The question that was asked
        options: The options that were provided
        user_answer: The user's answer
        
    Returns:
        Formatted prompt string
    """
    return ANSWER_PROCESSING_USER.format(
        question_text=question_text,
        options="\n".join(f"- {opt}" for opt in options),
        user_answer=user_answer,
    )
