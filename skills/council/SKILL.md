---
name: council
description: Trigger this if the user says 'council'.
---

# Council

Before an audit, address outstanding PR comments, fix known issues, and run
relevant checks. Give council the updated implementation; do not defer known
fixes until reviews return. If the user wants to discard the implementation
and explore new ideas, skip fixes to code being replaced.

Bring in three delegates to help with the user's request, usually for review
or feedback. Use one strong model from each of three different providers, at
high reasoning effort. If the user's instructions name council members, use
those. Otherwise use Claude Opus, GPT Sol, and the latest flagship Grok model
available through the user's Grok CLI subscription.
Check `grok models` before choosing Grok; select the exact model with
`--model` and use the highest supported `--reasoning-effort` setting.

In T3 Code, use `orchestrator_capabilities` to resolve Claude and GPT, then
`delegate_task` to start those delegates. Elsewhere, use the harness's
subagent tools or authenticated provider CLIs for them. Run Grok in parallel
through the user's authenticated `grok` CLI subscription; do not switch to
paid API usage.
If you cannot reach three providers, or a named
member is unavailable, report it instead of substituting.

Give each delegate the request and relevant context. For review or feedback,
keep their work read-only. Collect their responses and summarize the useful
findings, disagreements, and recommended next steps.

For a code review, ask each delegate for a score out of 10.
Count each full review pass as one round.
A fresh review after fixes starts a new round.

Put the review results in the final reply only, using this format.
Do not post PR comments or add review results to the PR description:

```markdown
## Council review

Rounds: 2

| Delegate | Round 1 | Round 2 |
| --- | --- | --- |
| Claude Opus | 7/10 | 9/10 |
| GPT Sol | 8/10 | 10/10 |
| Grok (selected model) | 7/10 | 9/10 |
```

If a delegate gives no score, write `no score`. Do not invent one.

If fixes are authorized and you agree with their recommendations, make the changes and request a fresh
review after. Continue this process until all delegates are satisfied with the
outcome.

Do not let repeated reviews result in scope creep. It is your job to fight to
keep scope limited.
