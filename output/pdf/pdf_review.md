## Review Summary

Clauses emitted: HARD=0  MEDIUM=8  SOFT=3  COMPILABLE=0

### Items requiring human review (NEEDS_REVIEW: true)
- [c-008] COMPILABLE_MEDIUM: You MUST perform all of these steps to ensure that the form is accurately completed.
- [c-011] COMPILABLE_MEDIUM: CRITICAL: Do not proceed without visually inspecting validation images.

### Low-confidence clauses (confidence < 0.6)
- [c-005] confidence=0.36: Create a `field_values.json` file in this format with the values to be entered for each field.
- [c-007] confidence=0.24: If the PDF doesn't have fillable form fields, you'll need to visually determine where the data shoul
- [c-010] confidence=0.36: Entry bounding boxes must be tall and wide enough to contain their text.

### Downgraded clauses (HARD → MEDIUM by capability profile)
- [c-002] COMPILABLE_MEDIUM: Run this script from this file's directory: `python scripts/check_fillable_fields <file.pdf>`
- [c-003] COMPILABLE_MEDIUM: If the PDF has fillable form fields: Run this script from this file's directory: `python scripts/ext
- [c-004] COMPILABLE_MEDIUM: Convert the PDF to PNGs (one image for each page) with this script (run from this file's directory):
- [c-006] COMPILABLE_MEDIUM: Run the `fill_fillable_fields.py` script from this file's directory to create a filled-in PDF.
