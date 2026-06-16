# Future Work

This document lists practical future improvements for Ledger Balance Tool. These are not current features unless explicitly stated in the codebase.

---

## 1. Matching Logic Improvements

Current matching is mainly amount-based. Future versions could improve candidate quality with additional signals:

- date proximity;
- vendor or counterparty extraction;
- voucher / reference number matching;
- account code or subject name matching;
- text similarity between descriptions;
- historical user confirmation patterns.

A useful next step would be a scoring model that ranks candidate pairs before they are shown to the user or sent to the LLM.

---

## 2. AI Output Validation

Current LLM handling requests JSON-array output and parses the response. This can be strengthened with stricter validation.

Potential improvements:

- define a strict response schema with Pydantic or `jsonschema`;
- validate required fields such as `pair_index`, `recommended`, and `reason`;
- reject out-of-range `pair_index` values;
- add retry logic for malformed JSON;
- separate parsing errors from API errors for better user feedback.

Confidence scores may be added to prioritize human review, but financial matches should remain human-confirmed rather than auto-approved.

---

## 3. Human-in-the-loop Workflow

The current flow keeps the user as the final decision-maker. Future UX improvements could include:

- batch review of multiple AI suggestions;
- better side-by-side comparison of candidate entries;
- clearer risk labels such as date mismatch, description mismatch, or combination match;
- undo / redo support for user actions;
- saved workflow progress between sessions.

---

## 4. Traceability and Operation Logs

The current system stores confirmed match records, but it does not yet implement a full operation audit log.

Future improvements could record:

- who triggered an operation;
- when the operation happened;
- which entries were affected;
- whether the match was rule-generated, AI-suggested, or manually confirmed;
- cancellation reasons;
- API call status, latency, and error messages.

This would make the workflow easier to debug and review.

---

## 5. Security

For local MVP usage, API settings are stored locally. For stronger security, future versions should consider:

- encrypted API key storage using `keyring` or an equivalent credential manager;
- masking sensitive values in logs and UI;
- a safer configuration workflow for shared machines;
- clear documentation for rotating or removing stored API keys.

---

## 6. Testing and Evaluation

Current tests cover core service and storage logic. Future testing could include:

- larger anonymized or synthetic ledger datasets;
- ground-truth reconciliation examples;
- precision, recall, and false-positive measurement for suggested matches;
- integration tests for import → matching → AI suggestion → confirmation → export;
- mocked LLM API responses for repeatable AI workflow tests;
- UI tests for critical user flows.

---

## 7. Performance Profiling

Before using the tool on large ledgers, performance should be measured and improved.

Potential areas:

- matching latency for 1k, 10k, and larger entry sets;
- combination search complexity;
- SQLite query performance;
- UI responsiveness during long operations;
- progress indicators or background workers for heavy tasks.

---

## 8. Possible Workflow Refactor

A future version could represent the workflow as a structured state graph, for example:

```text
import → normalization → rule-based matching → LLM semantic review → human approval → database update → export
```

A framework such as LangGraph could be considered for this type of stateful workflow in the future, especially if the project needs:

- clearer workflow composition;
- checkpoints and resumability;
- explicit human review nodes;
- better tracing of each step.

This is a future possibility only. The current implementation uses explicit Python service functions rather than a formal Agent framework.

---

## Near-term Priorities

The highest-value next steps are:

1. stricter JSON schema validation for AI responses;
2. better candidate ranking using date, reference, and description signals;
3. encrypted API key storage;
4. operation logs for traceability;
5. larger test datasets with evaluation metrics;
6. batch review UX for human confirmation.

These improvements would make the project more reliable without overstating it as a mature enterprise reconciliation system.

