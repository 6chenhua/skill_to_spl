---
name: sample_skill
description: A sample skill for testing the simplified pipeline
---

# Sample Skill

## Intent

This skill demonstrates the simplified pipeline by processing text inputs
and generating structured outputs. It is designed for testing purposes
and showcases the core workflow without external APIs or file operations.

## Workflow

1. Receive user input text describing a task
2. Validate the input format and content
3. Process the input using LLM reasoning
4. Generate a structured response
5. Validate the output format

If validation fails at any step, display an error message and request
user to fix the input.

## Constraints

- MUST validate input before processing
- MUST NOT proceed with empty input
- SHOULD provide clear error messages

## Examples

### Example 1: Basic Input Processing

Given: User provides "Create a summary of the document"
The skill should:
1. Validate the input is non-empty
2. Process using LLM reasoning
3. Return a structured summary object with fields: title, summary, key_points

### Example 2: Empty Input Handling

Given: User provides empty string
The skill should:
1. Detect empty input
2. Display error: "Input cannot be empty"
3. Request user to provide valid input

## Notes

- This is a test skill for pipeline validation
- Processing time depends on input complexity
- Results may vary based on input quality
