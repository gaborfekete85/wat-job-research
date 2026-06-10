You are scoring a job description against a candidate's profile.

# Candidate profile
{profile}

# Job description
Title: {title}
Company: {company}
Location: {location}
Seniority: {seniority}
Employment type: {employment_type}
Function: {job_function}
Industry: {industry}

{description}

# Pre-computed deterministic keyword overlap
- Keyword score: {keyword_score:.2f}
- Skills matched: {matched_skills}
- JD skills not in profile: {missing_skills}

# Instructions
Return STRICT JSON with these fields. Do not guess facts not present in the profile.

{{
  "final_score": <float 0.0–1.0>,             // overall match
  "skills_match": <float 0.0–1.0>,            // technical skills fit only
  "seniority_fit": "below" | "fit" | "above", // candidate vs JD seniority
  "location_fit": <bool>,
  "matched_skills": [<string>, ...],           // canonical names
  "missing_critical": [<string>, ...],         // skills the JD seems to require but profile lacks
  "reasoning": "<2–4 sentences, concrete>",
  "suggested_emphasis": {{
    "tailored_summary": "<2–3 sentences rewritten from profile.summary, JD-aware, no invented facts>",
    "priority_skills": [<canonical skill names, ordered by relevance to JD>],
    "priority_experiences": [<int indices into profile.experience, ordered by relevance>],
    "priority_bullets": {{ "<exp_idx>": [<int indices into highlights[]>] }}
  }}
}}

Be honest. If seniority is below, say so even if skills match. If the location is wrong, location_fit=false even if everything else fits.
