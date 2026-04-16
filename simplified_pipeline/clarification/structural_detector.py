"""
Structural Ambiguity Detector for HITL Clarification Module.

Detects statements that match patterns from multiple sections (INTENT, WORKFLOW,
CONSTRAINTS, EXAMPLES, NOTES), indicating structural assignment ambiguity.

This is fundamentally different from the old linguistic ambiguity detector:
- OLD: Detects "weak words" (appropriate, fast), pronouns (it, 它), quantifiers (many)
- NEW: Detects structural assignment ambiguity (which section should this go to?)

Example:
    Input: "你不直接回复用户，只负责输出一个数字"
    Detection: Matches both WORKFLOW and CONSTRAINTS patterns
    Result: StructuralAmbiguity with candidate_sections=["WORKFLOW", "CONSTRAINTS"]
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import List, Optional, Dict, Tuple, Set

from .structural_models import (
    StructuralAmbiguity,
    StructuralDetectionResult,
    SectionCategory,
)

logger = logging.getLogger(__name__)


class StructuralAmbiguityDetector:
    """
    Detects structural assignment ambiguity between Step 1 sections.
    
    A statement is structurally ambiguous if it matches patterns from multiple
    candidate sections (e.g., both WORKFLOW and CONSTRAINTS).
    
    Detection approach:
    1. Define section-specific regex patterns
    2. Check which section patterns match each statement
    3. If matches multiple sections, check ambiguity patterns
    4. Create StructuralAmbiguity with confidence score
    """
    
    # ═════════════════════════════════════════════════════════════════════════════
    # SECTION-SPECIFIC PATTERNS
    # ═════════════════════════════════════════════════════════════════════════════
    
    # Section-specific patterns (regex)
    # These patterns are designed for Chinese text in the skill-to-cnlp domain
    SECTION_PATTERNS: Dict[str, List[str]] = {
        "INTENT": [
            # System role definitions
            r"你是一个[^(，。!?)]+",  # "你是一个智能体调度系统"
            r"(?:目的|目标|旨在|用于)[是：].+",  # "目的是：", "目标是"
            r"负责[^(，。!?)]+",  # "负责根据流程判断"
            r"(?:定位|角色)[是：].*",  # "角色定位：MCN 品牌执行专员"
        ],
        "WORKFLOW": [
            # Action descriptions (not restrictions)
            r"(?:不)?直接(?:回复|输出|处理)",  # "不直接回复", "直接输出"
            r"(?:只|仅)负责",  # "只负责", "仅负责"
            r"步骤\d+|第\d+步",  # Numbered steps
            r"先.*再.*然后",  # Sequential indicators
            r"如果.*则|当.*时",  # Conditional flow (not constraint)
            r"→\s*\*\*[^*]+\*\*",  # Arrow to numbered dispatch
            r"\d+\s*=\s*[^=]+(?:智能体|助手)",  # "1 = 智能体A"
            r"(?:收集|跟进|传达|解答)",  # Action verbs
        ],
        "CONSTRAINTS": [
            # Restrictions, prohibitions, requirements
            r"当`[^`]+`\s*[＝=]\s*[^`]+`时",  # "当`type == 视频`时"
            r"(?:不能|禁止|不得|仅|只能)",  # Prohibitions, restrictions
            r"必须|MUST|SHALL",  # Mandatory language
            r"(?:仅|只)输出",  # "仅输出一个数字"
            r"(?:硬性|严格)",  # "硬性限制"
            r"(?:限制|约束|规则)",  # Explicit constraint language
        ],
        "EXAMPLES": [
            # Example indicators
            r"(?:例如|示例|比如)[：:]",  # "例如：", "示例:"
            r"\*\*[^*]+\*\*.*→",  # "**图文执行流程** →"
            r"典型场景",  # "典型场景："
        ],
        "NOTES": [
            # Supplementary information
            r"\*\*[^*]+=\s*[^*]+\*\*",  # "**1 = 智能体A**" (definitions)
            r"(?:说明|备注|注意)[：:]",  # "说明：", "注意："
            r"(?:注|注释)",  # "注：当消息同时满足..."
            r"[（(].*?:.*[）)]",  # Parenthetical explanations
        ],
    }
    
    # ═════════════════════════════════════════════════════════════════════════════
    # AMBIGUITY PATTERNS
    # ═════════════════════════════════════════════════════════════════════════════
    
    # Overlap patterns: statements matching multiple sections
    # These define specific ambiguous patterns and how to classify them
    AMBIGUITY_PATTERNS: List[Dict] = [
        {
            "name": "behavior_vs_constraint",
            "description": "Could describe behavior (workflow) or limitation (constraint)",
            "sections": ["WORKFLOW", "CONSTRAINTS"],
            "indicators": [
                # Behavior descriptions with restriction words
                r"(?:不)?直接.*(?:输出|回复|处理)",  # "不直接回复", "直接输出"
                r"(?:只|仅).*(?:输出|负责|能)",  # "只输出", "仅负责"
                r"(?:仅|只).*一个",  # "仅输出一个数字"
                r"(?:不)?.*(?:回复|输出)",  # General input/output
            ],
            "confidence_boost": 0.2,  # Boost confidence for this pattern
        },
        {
            "name": "procedure_vs_example",
            "description": "Could be workflow step or example",
            "sections": ["WORKFLOW", "EXAMPLES"],
            "indicators": [
                r"\d+\..*→",  # Numbered item with arrow
                r"(?:流程|步骤).*→",  # Flow with arrow
            ],
            "confidence_boost": 0.1,
        },
        {
            "name": "definition_vs_note",
            "description": "Could be intent definition or background note",
            "sections": ["INTENT", "NOTES"],
            "indicators": [
                r"\*\*[^*]+\*\*",  # Bold definitions
                r"(?:是|为)[：].*",  # "是一个智能体调度系统"
            ],
            "confidence_boost": 0.1,
        },
        {
            "name": "action_vs_constraint",
            "description": "Action description might be a constraint",
            "sections": ["WORKFLOW", "CONSTRAINTS"],
            "indicators": [
                r"(?:不能|禁止|不得)",  # Prohibitions in action context
            ],
            "confidence_boost": 0.15,
        },
    ]
    
    # ═════════════════════════════════════════════════════════════════════════════
    # DETECTION METHODS
    # ═════════════════════════════════════════════════════════════════════════════
    
    def __init__(self, confidence_threshold: float = 0.5):
        """
        Initialize detector.
        
        Args:
            confidence_threshold: Minimum confidence to consider ambiguous
        """
        self.confidence_threshold = confidence_threshold
        self._compiled_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for efficiency."""
        compiled = {}
        for section, patterns in self.SECTION_PATTERNS.items():
            compiled[section] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        return compiled
    
    def detect(self, text: str) -> StructuralDetectionResult:
        """
        Detect structural ambiguities in raw text.
        
        Args:
            text: The merged document text (before Step 1)
        
        Returns:
            StructuralDetectionResult with detected ambiguities
        """
        ambiguities: List[StructuralAmbiguity] = []
        
        # Split into statements/sentences
        statements = self._split_statements(text)
        logger.debug(f"Analyzing {len(statements)} statements for structural ambiguity")
        
        for stmt in statements:
            # Check which section patterns match
            matching_sections = self._get_matching_sections(stmt)
            
            # If matches multiple sections, check for ambiguity
            if len(matching_sections) >= 2:
                ambiguity = self._create_ambiguity(stmt, matching_sections)
                if ambiguity and ambiguity.confidence >= self.confidence_threshold:
                    ambiguities.append(ambiguity)
                    logger.debug(
                        f"Detected ambiguity: '{stmt[:50]}...' -> {matching_sections} "
                        f"(confidence: {ambiguity.confidence:.2f})"
                    )
        
        # Sort by confidence (highest first)
        ambiguities.sort(key=lambda x: x.confidence, reverse=True)
        
        return StructuralDetectionResult(
            ambiguities=ambiguities,
            total_statements=len(statements),
            ambiguous_statements=len(ambiguities),
        )
    
    def _split_statements(self, text: str) -> List[str]:
        """
        Split text into statements for analysis.
        
        Handles Chinese sentence boundaries.
        """
        # Split on sentence boundaries
        # Chinese: 。！？
        # Also split on newlines for structured docs
        delimiters = r'[。！？\n]+'
        statements = re.split(delimiters, text)
        
        # Filter and clean
        result = []
        for stmt in statements:
            stmt = stmt.strip()
            # Keep statements that are meaningful (not too short, not headers)
            if len(stmt) >= 10 and not stmt.startswith('#'):
                result.append(stmt)
        
        return result
    
    def _get_matching_sections(self, text: str) -> List[str]:
        """
        Get all sections whose patterns match this text.
        
        Returns list of section names that have at least one pattern match.
        """
        matching: List[str] = []
        
        for section, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    matching.append(section)
                    break  # Only need one match per section
        
        return matching
    
    def _create_ambiguity(
        self, 
        stmt: str, 
        sections: List[str]
    ) -> Optional[StructuralAmbiguity]:
        """
        Create StructuralAmbiguity if truly ambiguous.
        
        Uses ambiguity patterns to refine classification and confidence.
        """
        # Sort sections for consistent comparison
        sorted_sections = sorted(sections)
        
        # Check ambiguity patterns for better classification
        for amb_pattern in self.AMBIGUITY_PATTERNS:
            pattern_sections = sorted(amb_pattern["sections"])
            
            # Check if this matches the ambiguity pattern
            if sorted_sections == pattern_sections:
                # Check if any indicator matches
                for indicator in amb_pattern["indicators"]:
                    if re.search(indicator, stmt, re.IGNORECASE):
                        # Calculate confidence
                        confidence = self._calculate_confidence(
                            stmt, sections, amb_pattern.get("confidence_boost", 0)
                        )
                        
                        return StructuralAmbiguity(
                            ambiguity_id=f"amb_{uuid.uuid4().hex[:8]}",
                            source_text=stmt,
                            candidate_sections=sections,
                            ambiguity_reason=amb_pattern["description"],
                            confidence=confidence,
                            pattern_matched=amb_pattern["name"],
                        )
        
        # If no specific ambiguity pattern, but matches multiple sections
        # Create generic ambiguity with lower confidence
        confidence = self._calculate_confidence(stmt, sections, 0)
        
        if confidence >= self.confidence_threshold:
            return StructuralAmbiguity(
                ambiguity_id=f"amb_{uuid.uuid4().hex[:8]}",
                source_text=stmt,
                candidate_sections=sections,
                ambiguity_reason=f"Matches patterns from {', '.join(sections)}",
                confidence=confidence,
                pattern_matched="generic",
            )
        
        return None
    
    def _calculate_confidence(
        self, 
        stmt: str, 
        sections: List[str],
        boost: float = 0
    ) -> float:
        """
        Calculate confidence score for ambiguity.
        
        Higher confidence = more likely this is a real ambiguity.
        """
        # Base confidence: more sections = higher ambiguity
        base_conf = min(0.5 + (len(sections) - 2) * 0.15, 0.75)
        
        # Length factor: longer statements tend to have more context
        # But very long might be complex sentences
        length_factor = min(len(stmt) / 200, 0.1)
        
        # Pattern boost: specific patterns increase confidence
        pattern_boost = boost
        
        confidence = min(base_conf + length_factor + pattern_boost, 1.0)
        return confidence
    
    # ═════════════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═════════════════════════════════════════════════════════════════════════════
    
    def analyze_statement(self, text: str) -> Dict:
        """
        Analyze a single statement and return detailed info.
        
        Useful for debugging and testing.
        """
        matching = self._get_matching_sections(text)
        
        # Check for ambiguity
        is_ambiguous = len(matching) >= 2
        
        # Find which ambiguity patterns match
        pattern_matches = []
        if is_ambiguous:
            sorted_matching = sorted(matching)
            for amb_pattern in self.AMBIGUITY_PATTERNS:
                if sorted(amb_pattern["sections"]) == sorted_matching:
                    for indicator in amb_pattern["indicators"]:
                        if re.search(indicator, text, re.IGNORECASE):
                            pattern_matches.append(amb_pattern["name"])
                            break
        
        return {
            "text": text,
            "matching_sections": matching,
            "is_ambiguous": is_ambiguous,
            "pattern_matches": pattern_matches,
        }


# ═════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def detect_structural_ambiguities(
    text: str,
    confidence_threshold: float = 0.5
) -> StructuralDetectionResult:
    """
    Convenience function for structural ambiguity detection.
    
    Args:
        text: Text to analyze
        confidence_threshold: Minimum confidence threshold
    
    Returns:
        StructuralDetectionResult with detected ambiguities
    """
    detector = StructuralAmbiguityDetector(confidence_threshold)
    return detector.detect(text)


def analyze_for_sections(text: str) -> Dict[str, List[str]]:
    """
    Analyze text and show which sections each statement matches.
    
    Useful for debugging pattern matching.
    
    Args:
        text: Text to analyze
    
    Returns:
        Dict mapping statement to list of matching sections
    """
    detector = StructuralAmbiguityDetector()
    statements = detector._split_statements(text)
    
    results = {}
    for stmt in statements:
        sections = detector._get_matching_sections(stmt)
        if sections:
            results[stmt] = sections
    
    return results


__all__ = [
    "StructuralAmbiguityDetector",
    "detect_structural_ambiguities",
    "analyze_for_sections",
]
