# Deterministic edge-case playbook

The playbook is a catalog of small deterministic checks. Each check lives in a
single module under `packages/agent/src/argus/spec/checks/`; a module exports a
`CHECK` with its ID, category, applicability condition, case builder, and
expected behavior. The shared factory in `checks/common.py` keeps case IDs and
Pydantic construction consistent. Add one check by adding one module and one
entry to this document.

`generate(spec, elements)` evaluates each check against the current Explorer
element catalog, emits one case per matching visible control, and sorts checks
by module name and catalog order. With no catalog argument it loads the checked-in
Conduit catalog for offline runs. The generated cases use only semantic
locators from that catalog and validate as shared `TestCase` contracts.

## Forms

| ID | Check | Condition and expected behavior |
| --- | --- | --- |
| `form-empty-required` | Empty required field | Text input exists; required input is rejected with a clear message. |
| `form-max-length` | Maximum text length | Text input exists; excessive input is rejected without corruption. |
| `form-max-length-1024` | 1024-character text length | Text input exists; long input follows the documented field limit. |
| `form-max-length-10000` | 10000-character text length | Text input exists; long input is handled without a crash or corruption. |
| `form-unicode` | Unicode input | Text input exists; Unicode is handled without encoding loss. |
| `form-rtl-text` | Right-to-left text | Text input exists; right-to-left text remains intact and readable. |
| `form-negative-zero` | Negative and zero values | Text input exists; numeric boundary rules are respected. |
| `form-negative-number` | Negative number in a non-negative field | Text input exists; negative values follow the field's range rule. |
| `form-zero-number` | Zero numeric value | Text input exists; zero is handled at the lower boundary. |
| `form-decimal-integer` | Decimal in an integer field | Text input exists; decimals follow an explicit integer-field rule. |
| `form-whitespace-only` | Whitespace-only input | Text input exists; whitespace is normalized or rejected consistently. |
| `form-xss-payload` | XSS-shaped input | Text input exists; markup is treated as data. |
| `form-sql-payload` | SQL-shaped input | Text input exists; SQL-shaped text is treated as ordinary input. |
| `form-double-submit` | Double submission | A submit control exists; it receives one rapid double-click to check for duplicate mutations. |
| `form-back-mid-flow` | Back during a form flow | A text input is filled before browser back navigation. |
| `form-refresh-mid-flow` | Refresh during a form flow | A text input is filled, the associated submit control is clicked when available, then the page is reloaded. |
| `form-keyboard-submit` | Keyboard-only form submission | A text input is filled, Tab is pressed through catalogued controls, then Enter is pressed. |
| `form-mobile-viewport` | Mobile viewport form layout | A text input is exercised after resizing to 375×667. |
| `form-throttled-network` | Throttled network submission | A text input is filled and its form's submit control is clicked under a 3G profile. |
| `form-offline-toggle` | Offline toggle during request | A text input is filled, connectivity is disabled before submission, then restored after the request window. |
| `form-invalid-email` | Invalid email address | Text input exists; invalid email is rejected accessibly. |
| `form-numeric-boundary` | Numeric boundary values | Text input exists; bounds are enforced without overflow. |
| `form-duplicate-submit` | Rapid duplicate submit | Action control exists; repeated activation produces one operation. |
| `form-preserve-valid-input` | Preserve input after validation error | Text input exists; valid fields retain values after another field fails. |
| `form-password-masking` | Password field privacy | Text input exists; password remains masked in rendered text. |
| `form-validation-order` | Multiple field validation | Text input exists; relevant errors remain visible and attributable. |
| `form-optional-fields` | Omitted optional fields | Text input exists; omitting optional fields does not block valid submission. |

## Lists and navigation

| ID | Check | Condition and expected behavior |
| --- | --- | --- |
| `list-pagination-boundary` | Pagination boundaries | Button, link, or option exists; first/last page controls are correct. |
| `list-sort-stability` | Sort stability | A sort control inside a table header is exercised only when duplicate keys exist; tied-row order must survive a full direction cycle, otherwise the check is inconclusive. |
| `list-zero-result-filter` | Zero-result filter | A text filter is submitted with an unlikely match and the empty-state message is asserted. |
| `list-malformed-filter` | Malformed filter | Malformed filter text is submitted and new browser errors are rejected. |
| `list-long-item-name` | Long item names | Rendered long list text is checked for horizontal overflow; skipped when no long item is present. |
| `list-broken-links` | Broken links | Action control exists; links lead to intended in-app destinations. |
| `list-broken-images` | Broken images | Action control exists; missing images have a useful fallback. |
| `list-console-errors` | List console errors | Action control exists; interaction has no uncaught console errors. |
| `list-accessible-names` | Accessible list action names | Interactive controls are checked for missing accessible names. |
| `list-no-duplicate-pages` | Duplicate entries across pages | Action control exists; adjacent pages do not repeat items. |
| `list-empty-state` | Empty list state | Submits an unlikely filter query, then requires a recognizable empty-state message. |
| `list-filter-resets-page` | Filter resets pagination | Action control exists; filter changes return to a valid page. |
| `list-sort-direction` | Sort direction toggle | Action control exists; repeated sort toggles predictably. |
| `list-whitespace-filter` | Whitespace-only filter | Action control exists; whitespace is normalized. |
| `list-keyboard-navigation` | Keyboard list navigation | Action control exists; list controls support keyboard use. |
| `list-page-after-last` | Page beyond final result | Action control exists; invalid pages are not exposed. |
| `list-stale-row-action` | Action on stale list item | Action control exists; stale actions fail safely and refresh state. |
| `list-stable-item-identity` | Stable identity after sorting | Action control exists; sorting does not retarget row actions. |
| `list-refresh` | Refresh list state | Action control exists; reload returns consistent data and selection. |
| `list-large-page` | Large result page | Action control exists; large pages remain responsive and complete. |

## Cross-cutting security checks

| ID | Check | Condition and expected behavior |
| --- | --- | --- |
| `security-logged-out-protected` | Logged-out protected route | Opens `/account` in a fresh context and requires a redirect or explicit sign-in/denial feedback. |
| `security-idor` | Cross-account object access | Marked inconclusive unless the run has two authenticated users and a known owned-resource ID; no unsafe guess is made. |
| `security-reflected-xss` | Reflected XSS input | Text input exists; reflected markup cannot execute. |
| `security-session-expiry` | Expired session | Action control exists; expired sessions clear private data safely. |
| `security-open-redirect` | Untrusted redirect target | Text input exists; untrusted destinations cannot redirect off-site. |
| `security-csrf-state-change` | Cross-site state change | Action control exists; state changes require same-site protections. |

Environment setup actions (viewport, offline state, and Chromium 3G throttling)
are represented directly in the shared `Step` contract and handled by the
browser runner. The checks describe intended outcomes; dedicated outcome
oracles remain the responsibility of the oracle layer.
