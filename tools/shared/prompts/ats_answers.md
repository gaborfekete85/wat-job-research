You are drafting honest first-draft answers to common ATS application questions.

# Candidate profile
{profile}

# Job description
{job_block}

# Questions
{questions_block}

# Instructions
For each question, write a 1–3 sentence draft answer the candidate can edit.

Rules:
- ONLY use facts present in the candidate profile.
- For unknowable values (salary expectations, notice period, exact start date), use a TEMPLATE placeholder like `<TODO: confirm CHF range>` rather than guessing.
- For language proficiency, copy exactly from profile.languages.
- For work authorization, only state it if profile makes it explicit; otherwise `<TODO: confirm work authorization>`.

Return STRICT JSON: {{ "<question_id>": "<answer text>", ... }}
