"""
Ambiguity Detection Engine for HITL Clarification Module.

Implements hybrid detection combining rule-based patterns and LLM-based analysis.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import (
    AmbiguityMarker,
    AmbiguitySource,
    AmbiguityType,
    DetectionResult,
    SensitivityConfig,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# RULE-BASED PATTERNS (QuARS-inspired)
# ═════════════════════════════════════════════════════════════════════════════

# Weak words that indicate vague requirements (QuARS patterns)
WEAK_WORDS = {
    # English weak words
    "appropriate": AmbiguityType.WEAK_WORD,
    "suitable": AmbiguityType.WEAK_WORD,
    "adequate": AmbiguityType.WEAK_WORD,
    "sufficient": AmbiguityType.WEAK_WORD,
    "reasonable": AmbiguityType.WEAK_WORD,
    "proper": AmbiguityType.WEAK_WORD,
    "correct": AmbiguityType.WEAK_WORD,
    "necessary": AmbiguityType.WEAK_WORD,
    "relevant": AmbiguityType.WEAK_WORD,
    "acceptable": AmbiguityType.WEAK_WORD,
    "efficient": AmbiguityType.WEAK_WORD,
    "effective": AmbiguityType.WEAK_WORD,
    "timely": AmbiguityType.WEAK_WORD,
    "fast": AmbiguityType.PRAGMATIC,
    "slow": AmbiguityType.PRAGMATIC,
    "good": AmbiguityType.PRAGMATIC,
    "bad": AmbiguityType.PRAGMATIC,
    "simple": AmbiguityType.PRAGMATIC,
    "complex": AmbiguityType.PRAGMATIC,
    "easy": AmbiguityType.PRAGMATIC,
    "difficult": AmbiguityType.PRAGMATIC,
    # Chinese weak words
    "适当": AmbiguityType.WEAK_WORD,
    "合适": AmbiguityType.WEAK_WORD,
    "充分": AmbiguityType.WEAK_WORD,
    "合理": AmbiguityType.WEAK_WORD,
    "正确": AmbiguityType.WEAK_WORD,
    "必要": AmbiguityType.WEAK_WORD,
    "相关": AmbiguityType.WEAK_WORD,
    "可接受": AmbiguityType.WEAK_WORD,
    "高效": AmbiguityType.WEAK_WORD,
    "有效": AmbiguityType.WEAK_WORD,
    "及时": AmbiguityType.WEAK_WORD,
    "快速": AmbiguityType.PRAGMATIC,
    "简单": AmbiguityType.PRAGMATIC,
    "复杂": AmbiguityType.PRAGMATIC,
    "容易": AmbiguityType.PRAGMATIC,
    "困难": AmbiguityType.PRAGMATIC,
}

# Vague quantifiers
VAGUE_QUANTIFIERS = {
    # English
    "many": AmbiguityType.QUANTIFIER,
    "few": AmbiguityType.QUANTIFIER,
    "some": AmbiguityType.QUANTIFIER,
    "most": AmbiguityType.QUANTIFIER,
    "often": AmbiguityType.QUANTIFIER,
    "rarely": AmbiguityType.QUANTIFIER,
    "sometimes": AmbiguityType.QUANTIFIER,
    "usually": AmbiguityType.QUANTIFIER,
    "typically": AmbiguityType.QUANTIFIER,
    "generally": AmbiguityType.QUANTIFIER,
    "several": AmbiguityType.QUANTIFIER,
    "various": AmbiguityType.QUANTIFIER,
    "numerous": AmbiguityType.QUANTIFIER,
    "multiple": AmbiguityType.QUANTIFIER,
    # Chinese
    "许多": AmbiguityType.QUANTIFIER,
    "少量": AmbiguityType.QUANTIFIER,
    "一些": AmbiguityType.QUANTIFIER,
    "大多数": AmbiguityType.QUANTIFIER,
    "经常": AmbiguityType.QUANTIFIER,
    "很少": AmbiguityType.QUANTIFIER,
    "有时": AmbiguityType.QUANTIFIER,
    "通常": AmbiguityType.QUANTIFIER,
    "一般": AmbiguityType.QUANTIFIER,
    "多个": AmbiguityType.QUANTIFIER,
    "各种": AmbiguityType.QUANTIFIER,
}

# Optionality markers
OPTIONALITY_MARKERS = {
    # English
    "may": AmbiguityType.OPTIONALITY,
    "might": AmbiguityType.OPTIONALITY,
    "could": AmbiguityType.OPTIONALITY,
    "optionally": AmbiguityType.OPTIONALITY,
    "if needed": AmbiguityType.OPTIONALITY,
    "if possible": AmbiguityType.OPTIONALITY,
    "if applicable": AmbiguityType.OPTIONALITY,
    "where appropriate": AmbiguityType.OPTIONALITY,
    "where applicable": AmbiguityType.OPTIONALITY,
    "as needed": AmbiguityType.OPTIONALITY,
    "as appropriate": AmbiguityType.OPTIONALITY,
    "can": AmbiguityType.OPTIONALITY,
    "optional": AmbiguityType.OPTIONALITY,
    # Chinese
    "可以": AmbiguityType.OPTIONALITY,
    "可能": AmbiguityType.OPTIONALITY,
    "可选": AmbiguityType.OPTIONALITY,
    "如果需要": AmbiguityType.OPTIONALITY,
    "如果可能": AmbiguityType.OPTIONALITY,
    "如适用": AmbiguityType.OPTIONALITY,
    "视情况": AmbiguityType.OPTIONALITY,
    "必要时": AmbiguityType.OPTIONALITY,
}

# Pronouns that may have unclear antecedents
PRONOUNS = {
    # English
    "it": AmbiguityType.REFERENCE,
    "they": AmbiguityType.REFERENCE,
    "them": AmbiguityType.REFERENCE,
    "this": AmbiguityType.REFERENCE,
    "that": AmbiguityType.REFERENCE,
    "these": AmbiguityType.REFERENCE,
    "those": AmbiguityType.REFERENCE,
    "which": AmbiguityType.REFERENCE,
    "who": AmbiguityType.REFERENCE,
    "he": AmbiguityType.REFERENCE,
    "she": AmbiguityType.REFERENCE,
    "its": AmbiguityType.REFERENCE,
    "their": AmbiguityType.REFERENCE,
    # Chinese pronouns
    "它": AmbiguityType.REFERENCE,
    "它们": AmbiguityType.REFERENCE,
    "这": AmbiguityType.REFERENCE,
    "那": AmbiguityType.REFERENCE,
    "这些": AmbiguityType.REFERENCE,
    "那些": AmbiguityType.REFERENCE,
    "其": AmbiguityType.REFERENCE,
    "该": AmbiguityType.REFERENCE,
}

# Negation patterns (double negatives, unclear scope)
NEGATION_PATTERNS = [
    # English double negatives
    (r"\bnot\s+un\w+\b", AmbiguityType.NEGATION, "Double negative detected"),
    (r"\bnot\s+dis\w+\b", AmbiguityType.NEGATION, "Double negative detected"),
    (r"\bnever\s+not\b", AmbiguityType.NEGATION, "Double negative detected"),
    (r"\bno\s+non-\w+\b", AmbiguityType.NEGATION, "Double negative detected"),
    # Chinese negation patterns
    (r"不[不没]", AmbiguityType.NEGATION, "双重否定检测"),
    (r"[没无]不", AmbiguityType.NEGATION, "双重否定检测"),
    (r"非不", AmbiguityType.NEGATION, "双重否定检测"),
]

# Lexical ambiguity - words with multiple common meanings
LEXICAL_AMBIGUOUS = {
    # English
    "bank": AmbiguityType.LEXICAL,
    "green": AmbiguityType.LEXICAL,
    "light": AmbiguityType.LEXICAL,
    "right": AmbiguityType.LEXICAL,
    "left": AmbiguityType.LEXICAL,
    "run": AmbiguityType.LEXICAL,
    "set": AmbiguityType.LEXICAL,
    "file": AmbiguityType.LEXICAL,
    "plant": AmbiguityType.LEXICAL,
    "date": AmbiguityType.LEXICAL,
    "match": AmbiguityType.LEXICAL,
    "type": AmbiguityType.LEXICAL,
    "class": AmbiguityType.LEXICAL,
    "object": AmbiguityType.LEXICAL,
    "state": AmbiguityType.LEXICAL,
}


@dataclass
class RuleMatch:
    """Result of a rule-based pattern match."""

    text: str
    ambiguity_type: AmbiguityType
    explanation: str
    severity: float
    pattern_name: str
    start_pos: int
    end_pos: int


class RuleBasedDetector:
    """
    Rule-based ambiguity detector using pattern matching.

    Implements QuARS-inspired patterns for detecting:
    - Weak words (vague requirement terms)
    - Vague quantifiers
    - Optionality markers
    - Pronoun references
    - Negation patterns
    - Lexical ambiguity
    """

    def __init__(self, config: Optional[SensitivityConfig] = None):
        self.config = config or SensitivityConfig.medium()
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> list[tuple[re.Pattern, AmbiguityType, str]]:
        """Compile regex patterns for negation detection."""
        compiled = []
        for pattern, amb_type, explanation in NEGATION_PATTERNS:
            compiled.append((re.compile(pattern, re.IGNORECASE), amb_type, explanation))
        return compiled

    def scan_text(self, text: str, section_name: str, item_index: int) -> list[AmbiguityMarker]:
        """
        Scan text for rule-based ambiguity patterns.

        Args:
            text: Text to scan
            section_name: Name of the section containing this text
            item_index: Index of the SectionItem in the section

        Returns:
            List of AmbiguityMarker objects for detected ambiguities
        """
        markers = []
        text_lower = text.lower()

        # Check weak words
        markers.extend(self._check_word_list(
            text, text_lower, WEAK_WORDS, section_name, item_index, "weak_word"
        ))

        # Check vague quantifiers
        markers.extend(self._check_word_list(
            text, text_lower, VAGUE_QUANTIFIERS, section_name, item_index, "vague_quantifier"
        ))

        # Check optionality markers
        markers.extend(self._check_word_list(
            text, text_lower, OPTIONALITY_MARKERS, section_name, item_index, "optionality"
        ))

        # Check pronouns
        markers.extend(self._check_word_list(
            text, text_lower, PRONOUNS, section_name, item_index, "pronoun"
        ))

        # Check lexical ambiguity
        markers.extend(self._check_word_list(
            text, text_lower, LEXICAL_AMBIGUOUS, section_name, item_index, "lexical"
        ))

        # Check negation patterns
        markers.extend(self._check_negation_patterns(text, section_name, item_index))

        return markers

    def _check_word_list(
        self,
        text: str,
        text_lower: str,
        word_map: dict[str, AmbiguityType],
        section_name: str,
        item_index: int,
        pattern_name: str,
    ) -> list[AmbiguityMarker]:
        """Check for words from a word list."""
        markers = []

        for word, amb_type in word_map.items():
            # Find all occurrences
            start = 0
            word_lower = word.lower()
            while True:
                pos = text_lower.find(word_lower, start)
                if pos == -1:
                    break

                # Check word boundaries
                if self._is_word_boundary(text_lower, pos, len(word)):
                    # Extract the actual matched text (preserve case)
                    matched_text = text[pos:pos + len(word)]

                    severity = self._get_severity_for_type(amb_type)

                    markers.append(AmbiguityMarker(
                        source_text=matched_text,
                        ambiguity_type=amb_type,
                        severity=severity,
                        source=AmbiguitySource.RULE_BASED,
                        section_name=section_name,
                        source_item_index=item_index,
                        explanation=self._get_explanation(amb_type, matched_text),
                        suggestions=self._get_suggestions(amb_type, matched_text),
                        confidence=0.9,
                        detected_by=f"rule:{pattern_name}",
                    ))

                start = pos + 1

        return markers

    def _check_negation_patterns(
        self, text: str, section_name: str, item_index: int
    ) -> list[AmbiguityMarker]:
        """Check for negation pattern matches."""
        markers = []

        for pattern, amb_type, explanation in self._compiled_patterns:
            for match in pattern.finditer(text):
                markers.append(AmbiguityMarker(
                    source_text=match.group(),
                    ambiguity_type=amb_type,
                    severity=0.8,  # High severity for negation issues
                    source=AmbiguitySource.RULE_BASED,
                    section_name=section_name,
                    source_item_index=item_index,
                    explanation=explanation,
                    suggestions=["Rewrite to use positive phrasing", "Clarify the intended meaning"],
                    confidence=0.85,
                    detected_by="rule:negation_pattern",
                ))

        return markers

    def _is_word_boundary(self, text: str, pos: int, word_len: int) -> bool:
        """Check if position is at a word boundary."""
        # Check before - for Chinese, no word boundary needed
        if pos > 0:
            prev_char = text[pos - 1]
            # For Chinese characters, check if previous char is also Chinese
            if '\u4e00' <= prev_char <= '\u9fff':
                # Previous char is Chinese - this is a boundary for Chinese words
                pass
            elif prev_char.isalnum():
                return False
        
        # Check after - for Chinese, no word boundary needed
        if pos + word_len < len(text):
            next_char = text[pos + word_len]
            # For Chinese characters, check if next char is also Chinese
            if '\u4e00' <= next_char <= '\u9fff':
                # Next char is Chinese - this is a boundary for Chinese words
                pass
            elif next_char.isalnum():
                return False
        
        return True

    def _get_severity_for_type(self, amb_type: AmbiguityType) -> float:
        """Get default severity for an ambiguity type."""
        severity_map = {
            AmbiguityType.NEGATION: 0.8,
            AmbiguityType.CONFLICT: 0.9,
            AmbiguityType.REFERENCE: 0.6,
            AmbiguityType.WEAK_WORD: 0.5,
            AmbiguityType.QUANTIFIER: 0.5,
            AmbiguityType.OPTIONALITY: 0.4,
            AmbiguityType.LEXICAL: 0.6,
            AmbiguityType.PRAGMATIC: 0.5,
            AmbiguityType.SYNTACTIC: 0.7,
            AmbiguityType.SEMANTIC: 0.7,
            AmbiguityType.CONTEXT: 0.6,
        }
        return severity_map.get(amb_type, 0.5)

    def _get_explanation(self, amb_type: AmbiguityType, word: str) -> str:
        """Get explanation for an ambiguity type."""
        explanations = {
            AmbiguityType.WEAK_WORD: f"'{word}' is a vague term that lacks precise definition",
            AmbiguityType.QUANTIFIER: f"'{word}' is a vague quantifier without specific numbers",
            AmbiguityType.OPTIONALITY: f"'{word}' indicates uncertainty about requirement strength",
            AmbiguityType.REFERENCE: f"'{word}' may have an unclear antecedent",
            AmbiguityType.LEXICAL: f"'{word}' has multiple common meanings",
            AmbiguityType.PRAGMATIC: f"'{word}' is context-dependent and imprecise",
            AmbiguityType.NEGATION: "Double or unclear negation detected",
        }
        return explanations.get(amb_type, f"Ambiguity detected: {word}")

    def _get_suggestions(self, amb_type: AmbiguityType, word: str) -> list[str]:
        """Get suggestions for resolving ambiguity."""
        suggestions_map = {
            AmbiguityType.WEAK_WORD: [
                f"Replace '{word}' with specific criteria or measurable thresholds",
                "Define what constitutes acceptable/adequate in this context",
            ],
            AmbiguityType.QUANTIFIER: [
                f"Replace '{word}' with specific numbers or ranges",
                "Specify exact counts or percentages",
            ],
            AmbiguityType.OPTIONALITY: [
                "Clarify if this is required or optional",
                "Specify conditions under which this applies",
            ],
            AmbiguityType.REFERENCE: [
                "Replace pronoun with the specific noun it refers to",
                "Ensure the antecedent is clear from context",
            ],
            AmbiguityType.LEXICAL: [
                f"Clarify which meaning of '{word}' is intended",
                "Use a more specific term",
            ],
            AmbiguityType.PRAGMATIC: [
                f"Define specific criteria for '{word}'",
                "Provide measurable benchmarks",
            ],
        }
        return suggestions_map.get(amb_type, ["Clarify the intended meaning"])


# ═════════════════════════════════════════════════════════════════════════════
# LLM-BASED DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

AMBIGUITY_DETECTION_PROMPT = """\
Analyze the following requirement sections for ambiguity. Identify:
1. Words with multiple possible meanings
2. Vague or underspecified terms
3. Missing context or references
4. Conflicting or contradictory statements
5. Unclear scope or boundaries

For each ambiguity found, provide:
- The exact text causing ambiguity
- Type of ambiguity (lexical, syntactic, semantic, pragmatic, reference, context, conflict)
- Severity score (0.0-1.0, where 1.0 is critical)
- Why it's ambiguous
- Suggested clarification

Output as JSON array of ambiguities.

## Sections to Analyze:
{sections_text}

## Output Format:
Return a JSON object with this structure:
{{
  "ambiguities": [
    {{
      "source_text": "exact text",
      "ambiguity_type": "lexical|syntactic|semantic|pragmatic|reference|context|conflict",
      "severity": 0.0-1.0,
      "section_name": "INTENT|WORKFLOW|CONSTRAINTS|EXAMPLES|NOTES",
      "explanation": "why it's ambiguous",
      "suggestions": ["suggestion 1", "suggestion 2"]
    }}
  ],
  "overall_confidence": 0.0-1.0
}}

If no ambiguities found, return {{"ambiguities": [], "overall_confidence": 1.0}}
"""


class LLMBasedDetector:
    """
    LLM-based ambiguity detector using structured prompts.

    Uses LLM to identify complex ambiguities that rule-based
    patterns might miss.
    """

    def __init__(self, llm_client: Any, config: Optional[SensitivityConfig] = None):
        """
        Initialize LLM detector.

        Args:
            llm_client: LLM client with call_json method
            config: Sensitivity configuration
        """
        self.llm_client = llm_client
        self.config = config or SensitivityConfig.medium()

    def scan_bundle(
        self,
        section_bundle: Any,
        section_name: str = "",
        item_index: int = 0,
    ) -> tuple[list[AmbiguityMarker], float]:
        """
        Use LLM to detect ambiguities in a SectionBundle.

        Args:
            section_bundle: SectionBundle to analyze
            section_name: Current section being processed (for nested calls)
            item_index: Current item index (for nested calls)

        Returns:
            Tuple of (list of markers, overall confidence score)
        """
        # Render sections as text
        sections_text = section_bundle.to_text()

        if not sections_text.strip():
            return [], 1.0

        prompt = AMBIGUITY_DETECTION_PROMPT.format(sections_text=sections_text)

        try:
            response = self.llm_client.call_json(
                step_name="ambiguity_detection",
                system="You are an expert at identifying ambiguity in technical requirements. Analyze the text and identify any ambiguities. Respond with valid JSON only.",
                user=prompt,
            )

            return self._parse_llm_response(response, section_name, item_index)

        except Exception as e:
            logger.warning(f"LLM ambiguity detection failed: {e}")
            return [], 0.5

    def _parse_llm_response(
        self,
        response: dict,
        default_section: str,
        default_index: int,
    ) -> tuple[list[AmbiguityMarker], float]:
        """Parse LLM response into AmbiguityMarker objects."""
        markers = []

        ambiguities = response.get("ambiguities", [])
        overall_confidence = response.get("overall_confidence", 0.8)

        for item in ambiguities:
            try:
                amb_type_str = item.get("ambiguity_type", "pragmatic").lower()
                amb_type = self._map_ambiguity_type(amb_type_str)

                severity = float(item.get("severity", 0.5))
                severity = max(0.0, min(1.0, severity))

                markers.append(AmbiguityMarker(
                    source_text=item.get("source_text", ""),
                    ambiguity_type=amb_type,
                    severity=severity,
                    source=AmbiguitySource.LLM_BASED,
                    section_name=item.get("section_name", default_section),
                    source_item_index=item.get("item_index", default_index),
                    explanation=item.get("explanation", ""),
                    suggestions=item.get("suggestions", []),
                    confidence=0.8,
                    detected_by="llm:analysis",
                ))

            except Exception as e:
                logger.warning(f"Failed to parse ambiguity item: {e}")
                continue

        return markers, overall_confidence

    def _map_ambiguity_type(self, type_str: str) -> AmbiguityType:
        """Map string to AmbiguityType enum."""
        type_map = {
            "lexical": AmbiguityType.LEXICAL,
            "syntactic": AmbiguityType.SYNTACTIC,
            "semantic": AmbiguityType.SEMANTIC,
            "pragmatic": AmbiguityType.PRAGMATIC,
            "reference": AmbiguityType.REFERENCE,
            "context": AmbiguityType.CONTEXT,
            "conflict": AmbiguityType.CONFLICT,
            "negation": AmbiguityType.NEGATION,
            "optionality": AmbiguityType.OPTIONALITY,
            "quantifier": AmbiguityType.QUANTIFIER,
            "weak_word": AmbiguityType.WEAK_WORD,
        }
        return type_map.get(type_str.lower(), AmbiguityType.PRAGMATIC)


# ═════════════════════════════════════════════════════════════════════════════
# DEFECT DENSITY CALCULATOR
# ═════════════════════════════════════════════════════════════════════════════


def calculate_defect_density(markers: list[AmbiguityMarker], total_words: int) -> float:
    """
    Calculate defect density for triggering decision.

    Formula: defect_density = affected_words / total_words

    Args:
        markers: List of detected ambiguity markers
        total_words: Total word count in analyzed text

    Returns:
        Defect density ratio (0.0 to 1.0)
    """
    if total_words == 0:
        return 0.0

    # Count unique affected words (avoid double-counting overlapping text)
    affected_positions: set[tuple[int, int]] = set()

    for marker in markers:
        # Use source_text length as approximation
        word_count = len(marker.source_text.split())
        affected_positions.add((id(marker), word_count))

    affected_words = sum(count for _, count in affected_positions)

    # Normalize by total words
    density = affected_words / total_words
    return min(1.0, density)


def count_words(text: str) -> int:
    """
    Count words in text, handling both English and Chinese.

    For Chinese, counts characters as words (approximation).
    For English, splits on whitespace.
    """
    if not text:
        return 0

    # Check if text is primarily Chinese
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total_chars = len(text.replace(' ', '').replace('\n', ''))

    if total_chars > 0 and chinese_chars / total_chars > 0.5:
        # Primarily Chinese - count characters
        return chinese_chars
    else:
        # Primarily English - count words
        return len(text.split())


# ═════════════════════════════════════════════════════════════════════════════
# HYBRID AMBIGUITY DETECTOR
# ═════════════════════════════════════════════════════════════════════════════


class AmbiguityDetector:
    """
    Hybrid ambiguity detector combining rule-based and LLM-based detection.

    Detection flow:
    1. Rule-based scan for known patterns
    2. LLM confidence scoring for complex ambiguities
    3. Merge and deduplicate results
    4. Filter by severity threshold
    """

    def __init__(
        self,
        llm_client: Any = None,
        config: Optional[SensitivityConfig] = None,
    ):
        """
        Initialize the hybrid detector.

        Args:
            llm_client: Optional LLM client for LLM-based detection
            config: Sensitivity configuration
        """
        self.config = config or SensitivityConfig.medium()
        self.rule_detector = RuleBasedDetector(self.config)
        self.llm_detector = None

        if llm_client and self.config.enable_llm_based:
            self.llm_detector = LLMBasedDetector(llm_client, self.config)

    def detect(
        self,
        section_bundle: Any,
        llm_client: Any = None,
    ) -> DetectionResult:
        """
        Detect ambiguities in a SectionBundle.

        Args:
            section_bundle: SectionBundle to analyze
            llm_client: Optional override LLM client

        Returns:
            DetectionResult with markers and metrics
        """
        # Allow client override
        client = llm_client or (self.llm_detector.llm_client if self.llm_detector else None)

        # Step 1: Rule-based scan
        rule_markers = []
        if self.config.enable_rule_based:
            rule_markers = self._rule_based_scan(section_bundle)

        # Step 2: LLM confidence scoring
        llm_markers = []
        llm_confidence = 1.0
        if self.config.enable_llm_based and client:
            llm_markers, llm_confidence = self._llm_confidence_scan(section_bundle, client)

        # Step 3: Merge and deduplicate
        all_markers = self._merge_markers(rule_markers, llm_markers)

        # Step 4: Filter by severity threshold
        filtered_markers = [
            m for m in all_markers
            if m.severity >= self.config.severity_threshold
        ]

        # Calculate metrics
        total_words = self._count_total_words(section_bundle)
        affected_words = sum(len(m.source_text.split()) for m in filtered_markers)
        defect_density = calculate_defect_density(filtered_markers, total_words)

        # Determine if clarification needed
        needs_clarification = (
            defect_density > self.config.defect_density_threshold
            or llm_confidence < self.config.confidence_threshold
        )

        return DetectionResult(
            markers=filtered_markers,
            defect_density=defect_density,
            total_words=total_words,
            affected_words=affected_words,
            needs_clarification=needs_clarification,
            confidence_score=llm_confidence,
        )

    def _rule_based_scan(self, section_bundle: Any) -> list[AmbiguityMarker]:
        """Perform rule-based scan on all sections."""
        markers = []

        sections = section_bundle.all_sections()
        for section_name, items in sections.items():
            for idx, item in enumerate(items):
                item_markers = self.rule_detector.scan_text(
                    text=item.text,
                    section_name=section_name,
                    item_index=idx,
                )
                markers.extend(item_markers)

        return markers

    def _llm_confidence_scan(
        self,
        section_bundle: Any,
        client: Any,
    ) -> tuple[list[AmbiguityMarker], float]:
        """Perform LLM-based confidence scan."""
        if not self.llm_detector:
            self.llm_detector = LLMBasedDetector(client, self.config)

        return self.llm_detector.scan_bundle(section_bundle)

    def _merge_markers(
        self,
        rule_markers: list[AmbiguityMarker],
        llm_markers: list[AmbiguityMarker],
    ) -> list[AmbiguityMarker]:
        """Merge and deduplicate markers from different sources."""
        if not self.config.merge_overlapping:
            return rule_markers + llm_markers

        # Create a map of text positions to markers
        merged: list[AmbiguityMarker] = []
        seen_texts: set[str] = set()

        # Add rule-based markers first (higher confidence for known patterns)
        for marker in rule_markers:
            text_key = f"{marker.section_name}:{marker.source_text.lower()}"
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                merged.append(marker)

        # Add LLM markers that don't overlap
        for marker in llm_markers:
            text_key = f"{marker.section_name}:{marker.source_text.lower()}"
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                merged.append(marker)
            else:
                # Merge with existing marker - update to hybrid source
                for existing in merged:
                    if f"{existing.section_name}:{existing.source_text.lower()}" == text_key:
                        # Create hybrid marker
                        existing.source = AmbiguitySource.HYBRID
                        existing.confidence = min(1.0, existing.confidence + 0.1)
                        break

        return merged

    def _count_total_words(self, section_bundle: Any) -> int:
        """Count total words in all sections."""
        total = 0
        sections = section_bundle.all_sections()
        for items in sections.values():
            for item in items:
                total += count_words(item.text)
        return total


# ═════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════


def detect_ambiguities(
    section_bundle: Any,
    llm_client: Any = None,
    sensitivity: str = "medium",
) -> DetectionResult:
    """
    Convenience function for ambiguity detection.

    Args:
        section_bundle: SectionBundle to analyze
        llm_client: Optional LLM client
        sensitivity: "low", "medium", or "high"

    Returns:
        DetectionResult with markers and metrics
    """
    config_map = {
        "low": SensitivityConfig.low(),
        "medium": SensitivityConfig.medium(),
        "high": SensitivityConfig.high(),
    }
    config = config_map.get(sensitivity, SensitivityConfig.medium())

    detector = AmbiguityDetector(llm_client=llm_client, config=config)
    return detector.detect(section_bundle, llm_client)
