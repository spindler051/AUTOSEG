# User feedback guide

This guide is for observing real people using AUTOSEG and turning what they do
into product decisions. It complements `docs/HUMAN_CENTERED_DECISIONS.md`.

The goal is not to ask “do you like this feature?”. The goal is to understand
the work, the friction and the trust requirements.

## 1. Principles

1. **Observe real work, not a demo.** Ask the person to perform a real task they
   already need to do.
2. **Ask about the past, not hypotheticals.** “What did you do last time?” is
   more reliable than “Would you use this?”.
3. **Do not lead.** Avoid showing the feature and asking “isn’t this better?”.
4. **Separate problem from solution.** A request for a button may hide a
   workflow problem.
5. **Record exact words.** Quotes preserve context better than summaries.
6. **Consent and privacy.** No production data, client names, CPF/CNPJ, emails
   or screenshots with personal data without explicit permission.
7. **Human values are not telemetry.** Usage counts can show where people click;
   they cannot explain why a workflow feels unsafe or wrong.

## 2. Session script (20–30 minutes)

### Before

- Use a test database or a copy with anonymized data.
- Ask permission to take notes. Do not record audio/video without consent.
- Define one or two real tasks for the session.

### During

1. **Context**
   - What kind of work do you do?
   - How do you organize clients, jobs, payments and documents today?
   - What is the most stressful part of that work?

2. **Recent task walkthrough**
   - Tell me about the last time you did this task.
   - What did you use? What steps did you take?
   - Where did you have to remember something or write it down elsewhere?

3. **Observed task**
   - Please perform this task in AUTOSEG as you normally would.
   - Think aloud if comfortable.
   - Do not help immediately. Note hesitation, wrong turns, repeated clicks,
     reading, questions and workarounds.

4. **Friction**
   - What did you expect to happen here?
   - What were you trying to accomplish?
   - What would you do if the software did not let you continue?
   - Was there a moment you did not trust the result? Why?

5. **Value and trade-offs**
   - Which part saves you the most time?
   - Which part feels risky or bureaucratic?
   - If you could remove one step, which one? What would break?

6. **Close**
   - Is there anything I should have asked but didn’t?
   - May I contact you later to validate a prototype?

## 3. What to record

For each observation:

```text
Date / session:
Participant profile (no personal data):
Task:
What the person expected:
What happened:
Friction / confusion:
Workaround:
Exact quote:
Severity (low / medium / high):
Frequency (once / occasional / every time):
Trust or data-safety concern:
```

## 4. How feedback becomes a decision

1. **Tag the user impact** in the issue or PR.
2. Look for patterns across sessions, not a single request.
3. Write a short problem statement before proposing a feature.
4. For reversible changes, build a prototype or feature flag.
5. For irreversible choices, write an ADR using
   `docs/HUMAN_CENTERED_DECISIONS.md`.
6. Update `docs/PLATFORM_MIGRATION_LEDGER.md` if the feedback changes the next
   slice.
7. Tell the participant what changed, if they agreed to follow-up.

## 5. Pilot group

A useful pilot group is small but diverse:

- a security/automation operator (current AUTOSEG user);
- an electrician or maintenance technician;
- an artist or stagehand;
- a musician or DJ;
- an administrator who handles clients and payments.

The point is not to make AUTOSEG generic immediately. It is to discover which
concepts are truly generic and which are vertical.

## 6. Anti-patterns

- Asking “would you use this?” instead of observing a real task.
- Treating the loudest request as the most important need.
- Designing a plugin system before a second real consumer exists.
- Using telemetry as a substitute for trust, context and values.
- Recording personal or client data without consent.
- Turning every session into a feature list without a problem statement.

## 7. Related documents

- `docs/HUMAN_CENTERED_DECISIONS.md`
- `docs/PRODUCT_VISION.md`
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/PLATFORM_MIGRATION_LEDGER.md`
