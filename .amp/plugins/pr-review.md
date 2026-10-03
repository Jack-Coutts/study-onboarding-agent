# Label-triggered PR reviews

The `pr-review.ts` plugin accepts signed GitHub `pull_request` webhooks for
`Jack-Coutts/study-onboarding-agent`. Applying the exact label **ready for review** to an
open, non-draft PR launches a private Amp review orb in `medium` mode. The person
applying the label must currently have write, maintain, or admin permission.

The review pins the live base/head commits when dispatching and includes
SHA-256-identified snapshots of the owner's local `reviewing-prs` and
`reviewing-pr-simplicity` skills and trusted Python comment publisher. It does
not depend on those unpushed files already being on `origin/main`.

The same reviewer runs two sequential passes in one private Amp thread:

1. Scientific/correctness review, posted as its own PR conversation comment.
2. Only after the first comment is confirmed on GitHub, the simplicity skill
   reviews unnecessary tests, unused code, and avoidable complexity. It posts
   a separate **Simplicity follow-up** comment linking the first feedback.

This is a second focused pass, not an independent model panel. Both use the same
pinned scope, report results in Amp, and send a summary/comment links to the
webhook owner. The trusted publisher refuses an out-of-order follow-up, checks
authenticated-author delivery markers across all comment pages before writing,
and reads back after an ambiguous acknowledgement instead of blindly retrying.
If posting fails, the reviewer stops the sequence and reports the blocker.
Comments use the authenticated `gh` account. No code changes, test deletions,
approvals, merges, or public artifact uploads are authorized. Reviews consume
Amp/orb credits. `medium` is a mode, not an immutable model-version pin.

The skill requires test results, replay-run status and output checks,
and reviewer-generated, inspected visual evidence for affected UI and figures.
PR code must execute in credential-free isolation; a fresh orb alone does not
satisfy that requirement. If safe execution/rendering is unavailable, the review
must disclose the limitation instead of claiming verification.

## Local registration

The owning orb has an owner-only, gitignored `.amp/pr-review/config.json` with
`repositoryId` and a random 32-byte hex `secret`. Do not print or commit it.
Loading the plugin registers the stable key `ready-for-review` and writes its
capability URL to owner-only `.amp/pr-review/endpoint.json`. Treat that URL as
a credential too. Configure a GitHub repository webhook with this URL, the same
signing secret, JSON content type, SSL verification enabled, and only the
`pull_request` event. GitHub's initial ping is checked and recorded in
`.amp/pr-review/last-ping.json`; HTTP 200 alone only confirms Amp queued delivery.

Keep the owning Amp thread **unarchived**. A sleeping orb wakes on delivery;
archiving the owner makes the endpoint unavailable. Local files survive ordinary
pause/resume but are not a backup against orb loss. The source/skill must be
committed and published separately to make them recoverable in new checkouts;
credentials must be securely provisioned separately, never committed. Other
orbs without the local configuration do not register the webhook.

## Triggering and recovery

- Apply `ready for review` after marking the PR non-draft. Existing labelled PRs
  are not backfilled. New commits while the label remains do not trigger another
  review: remove and reapply the label to request one.
- The SHA-256 of the signed body deduplicates retries. GitHub signs only the
  body, so a delivery ID could be changed to replay a request; GitHub
  redeliveries resend the same body, and a reapplied label changes the PR's
  `updated_at`. Local dispatch records live in `.amp/pr-review/events/`;
  successful records include the review thread ID. Appends are recovered by
  checking the thread's initial messages for the delivery marker, after the
  same permission and live PR checks as a first dispatch.
- If thread creation has an unknown outcome, the record stays `creating` and
  the plugin logs that manual recovery is required. The API offers no atomic
  create-and-record transaction/idempotency key: this conservative choice avoids
  blindly creating duplicate paid reviews. Inspect Amp threads before repairing
  a record or requesting another review. Never delete records just to retry an
  operation whose outcome is unknown.
- Retryable API errors before creation are redelivered by Amp; handlers have a
  30-second deadline and observe cancellation. Signature failures, unrelated
  labels/events/repos, closed/draft PRs, and unauthorised senders are ignored.

Run offline contract tests without creating real review threads or GitHub comments:

```bash
make webhook-tests  # needs Bun
uv run --frozen pytest -ra tests/test_pr_review_publishing.py
```
