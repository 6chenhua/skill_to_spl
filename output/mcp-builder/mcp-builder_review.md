## Review Summary

Clauses emitted: HARD=0  MEDIUM=7  SOFT=3  COMPILABLE=0

### Items requiring human review (NEEDS_REVIEW: true)
- [c-002] COMPILABLE_MEDIUM: Use consistent prefixes (e.g., `github_create_issue`, `github_list_repos`) and action-oriented namin
- [c-006] COMPILABLE_MEDIUM: Use Zod (TypeScript) or Pydantic (Python)
- [c-010] COMPILABLE_MEDIUM: Questions must be READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE

### Low-confidence clauses (confidence < 0.6)
- [c-001] confidence=0.11: When uncertain, prioritize comprehensive API coverage.
- [c-002] confidence=0.56: Use consistent prefixes (e.g., `github_create_issue`, `github_list_repos`) and action-oriented namin
- [c-003] confidence=0.11: Error messages should guide agents toward solutions with specific suggestions and next steps.
- [c-006] confidence=0.56: Use Zod (TypeScript) or Pydantic (Python)
- [c-007] confidence=0.11: Include constraints and clear descriptions
- [c-010] confidence=0.56: Questions must be READ-ONLY, INDEPENDENT, NON-DESTRUCTIVE

### Downgraded clauses (HARD → MEDIUM by capability profile)
- [c-004] COMPILABLE_MEDIUM: Start with the sitemap to find relevant pages: `https://modelcontextprotocol.io/sitemap.xml`
- [c-005] COMPILABLE_MEDIUM: Then fetch specific pages with `.md` suffix for markdown format (e.g., `https://modelcontextprotocol
- [c-008] COMPILABLE_MEDIUM: Run `npm run build` to verify compilation
- [c-009] COMPILABLE_MEDIUM: Test with MCP Inspector: `npx @modelcontextprotocol/inspector`
