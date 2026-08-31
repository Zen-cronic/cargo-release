# Upstream contribution — ADK Express Mode client migration

**Status:** [PR #2187 OPEN](https://github.com/google/adk-docs/pull/2187) — Google CLA pending
**Target:** [`google/adk-docs`](https://github.com/google/adk-docs)
**Observed:** 2026-08-31 at ADK docs commit
`1203686bb4a30351393d3bccea06abd91f008e19`
**Verified SDK:** `google-cloud-aiplatform[agent_engines]==1.165.1`

The verified patch was filed as PR #2187. The fallback issue below was deliberately not opened,
because filing both artifacts would duplicate the same actionable fix.

## Finding

[`docs/integrations/express-mode.md`](https://github.com/google/adk-docs/blob/1203686bb4a30351393d3bccea06abd91f008e19/docs/integrations/express-mode.md#L53-L74)
imports `vertexai` and constructs `vertexai.Client(...)`. Released
`google-cloud-aiplatform==1.165.1` emits:

```text
FutureWarning: The vertexai.Client class is deprecated. Please use agentplatform.Client instead.
```

The released replacement is `agentplatform.Client`. In version `1.165.1`, its runtime collection
is still `client.agent_engines`; the `client.runtimes` rename exists on the SDK's unreleased `main`
branch but not in the pinned release. The prepared patch therefore changes only the import and
client constructor and deliberately retains the released `agent_engines` API.

This surfaced while Cargo Release integrated managed Agent Runtime and Memory Bank.

## Verification receipt

Run against `google-cloud-aiplatform[agent_engines]==1.165.1`:

```text
old_warnings= ['The vertexai.Client class is deprecated. Please use agentplatform.Client instead.']
new_warnings= []
agent_engines_type= AgentEngines
has_create= True
has_runtimes= False
```

The check constructs each client with a non-secret test API key and inspects the released
collection without sending a network request or creating a runtime. Before filing, rerun this
check and, if an Express Mode test key is available, execute the documented runtime creation in a
disposable project.

The prepared patch also passed `git apply --check`, `git diff --check`, and the upstream repository's
full `mkdocs build --strict` at commit `1203686bb4a30351393d3bccea06abd91f008e19`.

## Duplicate preflight — rerun immediately before filing

- Current `google/adk-docs/main` still contains the deprecated constructor at commit
  `1203686bb4a30351393d3bccea06abd91f008e19`.
- The most recently updated 200 issues contained no report matching the rare client identifiers.
- The current open PR set contained one neighbour:
  [`google/adk-docs#2019`](https://github.com/google/adk-docs/pull/2019).
- PR #2019 changes `google-adk[vertexai]` to `google-adk[gcp]` and fixes a Memory Bank link in the
  same page. It does not touch lines 53–74, `vertexai.Client`, or `agentplatform.Client`.
- Recent sibling `googleapis/python-aiplatform` issues do not report this documentation mismatch.
- Stance: **PARALLEL**, with one-page rebase risk. Churn cost: one PR or one issue.

## Prepared PR

### Title

```text
docs(integrations): use Agent Platform client in Express Mode example
```

### Patch

Apply [the prepared patch](adk-docs-express-mode-agentplatform.patch) from a fresh
`google/adk-docs` checkout:

```bash
git apply /absolute/path/to/cargo-release/docs/adk-docs-express-mode-agentplatform.patch
```

### Body

````markdown
### What

Use `agentplatform.Client` in the Express Mode Agent Runtime example instead of the deprecated
`vertexai.Client` entry point.

### Why

Running the documented client construction with `google-cloud-aiplatform==1.165.1` emits:

```text
FutureWarning: The vertexai.Client class is deprecated. Please use agentplatform.Client instead.
```

The page currently directs new Express Mode users through that deprecated constructor.

### How

- Import `agentplatform` instead of `vertexai`.
- Construct `agentplatform.Client` with the existing Express Mode API key.
- Retain `client.agent_engines.create(...)`, which is the runtime collection exposed by the
  released `1.165.1` SDK.

### Test

With `google-cloud-aiplatform[agent_engines]==1.165.1`:

```text
vertexai.Client warnings: [FutureWarning: ... use agentplatform.Client instead.]
agentplatform.Client warnings: []
agentplatform.Client.agent_engines: AgentEngines
agentplatform.Client.agent_engines.create: present
```

The check constructs the clients without sending a request. I also confirmed the edited snippet is
valid Python. Runtime creation itself still requires an Express Mode API key.

```text
git apply --check: passed
git diff --check: passed
mkdocs build --strict: passed (230 pages indexed)
```

### Scope

This changes only the deprecated client entry point in the Express Mode creation example. It does
not migrate other pages or adopt the unreleased `client.runtimes` rename.

### Related

PR #2019 updates installation extras and a link later in this page. It does not change the client
constructor, so this is a separate correction.
````

### Filed PR

- PR: <https://github.com/google/adk-docs/pull/2187>
- Fork branch: <https://github.com/Zen-cronic/adk-docs/tree/docs/express-mode-agentplatform>
- Commit: <https://github.com/google/adk-docs/pull/2187/commits/50f02aa94efa570740d15e2bfe5236a0613f5b3b>
- Current state at filing: open and mergeable; Google CLA check pending operator completion.

## Prepared fallback issue

### Title

```text
Express Mode guide constructs deprecated vertexai.Client
```

### Body

````markdown
### What happens

`docs/integrations/express-mode.md` tells Express Mode users to construct `vertexai.Client(...)`,
which emits a deprecation warning in the released Agent Platform SDK.

### Reproduction

With `google-cloud-aiplatform[agent_engines]==1.165.1`:

```py
import warnings
import vertexai

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    vertexai.Client(api_key="test-only")

print([str(item.message) for item in caught])
```

Actual output:

```text
['The vertexai.Client class is deprecated. Please use agentplatform.Client instead.']
```

Replacing the import and constructor with `agentplatform.Client` produces no warning, while
`client.agent_engines.create` remains available in `1.165.1`.

### Why it matters

The current Express Mode onboarding example starts new users on a deprecated entry point even
though the released replacement accepts the same API-key authentication flow.

### Root cause

The example at `docs/integrations/express-mode.md` lines 53–74 predates the public
`agentplatform.Client` namespace. The minimal released-SDK correction changes the import and client
constructor while retaining `client.agent_engines`.

### Environment

- `google-cloud-aiplatform[agent_engines]==1.165.1`
- ADK docs commit `1203686bb4a30351393d3bccea06abd91f008e19`
- Python 3.12

### Related

PR #2019 edits the same page but changes installation extras and a Memory Bank link after this
example. It does not migrate `vertexai.Client`, so this is a distinct documentation mismatch.

Happy to open the two-line migration as a narrowly scoped PR.
````

### Manual issue URL

Open <https://github.com/google/adk-docs/issues/new>, paste the prepared title and body, preview it,
and submit manually. Merely opening this link does not create an issue.

## Operator filing checklist

- [x] Pull current `google/adk-docs/main` and record its SHA.
- [x] Confirm the target lines still use `vertexai.Client`.
- [x] Confirm PR #2019 or a newer PR has not migrated those exact lines.
- [x] Reinstall or verify `google-cloud-aiplatform[agent_engines]==1.165.1` in a disposable env.
- [x] Apply the patch and rerun the warning/property check.
- [x] Run the repository's documented Markdown/MkDocs checks.
- [x] Prefer the PR; do not file the duplicate fallback issue.
- [x] File under the operator's GitHub identity.
- [x] Copy the real PR URL into Devpost/README after GitHub shows it exists.
- [ ] Complete the Google CLA and confirm the check reruns successfully.
- [x] Describe the state as `open`, never `accepted` or `merged` unless GitHub proves that state.
