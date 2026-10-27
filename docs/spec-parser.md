# Product specification parser

`argus.spec.parser.ModelSpecParser` converts a product description and optional
supporting text (README, OpenAPI excerpt, or user stories) to the shared `Spec`
contract. It makes one structured call on the `cheap` model tier through
`ModelGateway`. The gateway validates the response against the Pydantic-derived
JSON Schema, records/replays the complete request in cassette modes, and retries
malformed structured output once. If the retry is invalid, parsing raises
`MalformedModelResponse` and returns no partial result.

The prompt is `SYSTEM_PROMPT` in `argus/spec/parser.py`. It asks the model to
preserve source facts, produce actionable semantic journeys, separate testable
claims, and extract entities, validation rules, and authentication requirements.
For Conduit, it explicitly requests at least six journeys including sign-up,
login, and article creation. Supporting material is included in sorted name
order, making the request and its cassette key reproducible.

Claim IDs are replaced after validation with `claim-` plus the first 16
hexadecimal characters of SHA-256 over the NFKC-normalized, case-folded,
whitespace-collapsed statement. Thus model-generated IDs and formatting changes
do not change claim identity. Duplicate normalized claims collapse to one claim.
Each claim's `journey_ids` links its validation journeys; the parser projects
those stable claim IDs onto each journey's `claim_ids` for reusable-test
traceability.

Use the async API:

```python
parser = ModelSpecParser(gateway, run_id="run-123")
spec = await parser.parse(description, {"README.md": readme_text})
```

In a live run, `argus --url ... --spec ...` invokes the parser before test
generation. Supply context files with repeated `--context README.md
--context openapi.yaml` options. When explicit `--journeys` JSON is supplied,
the parser call is skipped while playbook generation and binding still run.
The API accepts supporting material as a `context` object of filename-to-text
entries. Parsing requires a configured `cheap` model route. The role can also
be selected in the offline walking skeleton with `argus --stubs --real
spec_parser`; configure cassette mode using the `ARGUS_MODEL_*` settings
documented in the agent README.
