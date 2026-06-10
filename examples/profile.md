---
# Personal info — shown at the top of your tailored CV.
# Fill in YOUR details; this file is the source of truth for the matcher
# (against JDs) and the tailor (it picks which experience bullets to lead with).
name: "Your Full Name"
title: "Senior Software Engineer"
email: "you@example.com"
phone: "+1 555 0100"
location: "City, Country"
linkedin: "https://www.linkedin.com/in/your-handle/"
github: "https://github.com/your-handle"
website: "https://yourdomain.com/portfolio"
summary: >
  2-3 sentences describing who you are professionally. The tailor may rewrite this
  per-job based on the LLM match-result's `suggested_emphasis.tailored_summary`,
  but only when LLM scoring is enabled (requires ANTHROPIC_API_KEY). Without it
  this summary is used verbatim.

# Skills — list as many as you like. The matcher scores against these.
# Group them so the CV reads well; the regex matcher is category-agnostic.
skills:
  languages:
    - Python
    - JavaScript
    - TypeScript
    - SQL
  frameworks:
    - FastAPI
    - React
    - Node.js
    - Kafka
  cloud_devops:
    - AWS
    - Docker
    - Kubernetes
    - Terraform
    - CI/CD
  databases:
    - PostgreSQL
    - MongoDB
    - Redis
  tools:
    - Git
    - Linux
    - Jira
  soft:
    - Team leadership
    - Mentoring
    - Agile / Scrum
    - Cross-functional collaboration

# Work history — most recent first.
# `highlights` should be concrete, outcome-oriented bullets (use numbers where you can).
# `keywords` is a free-form list of tech/skills used in this role — the matcher reads these too.
experience:
  - company: "Current Company"
    role: "Senior Software Engineer"
    start: "2023-01"
    end: "Until now"
    location: "City, Country"
    highlights:
      - "Led a 3-person team migrating the core service from monolith to microservices on Kubernetes."
      - "Cut p99 latency from 800ms to 120ms by introducing a Redis-backed cache layer."
      - "Established Test-Driven Development practices, lifting code coverage from 35% to 78%."
    keywords: [Python, FastAPI, Kubernetes, Redis, PostgreSQL]

  - company: "Previous Company"
    role: "Software Engineer"
    start: "2020-06"
    end: "2022-12"
    location: "City, Country"
    highlights:
      - "Built an event-driven order pipeline on Kafka handling 50k events/min."
      - "Owned migrations from on-prem to AWS (ECS, RDS, S3) for a team of 12."
    keywords: [Java, Spring, Kafka, AWS]

# Education
education:
  - school: "Your University"
    degree: "MSc Computer Science"
    start: "2014"
    end: "2019"
    location: "City, Country"

# Certifications / courses (optional)
certifications:
  - name: "AWS Certified Solutions Architect – Associate"
    issuer: "Amazon Web Services"
    year: "2024"

# Languages (optional)
languages:
  - { name: "English", level: "Fluent" }
  - { name: "Your-native", level: "Native" }

# Projects / side work (optional)
projects:
  - "Side project: open-source CLI for X"
  - "Hackathon win: real-time something"
---

# Long-form background (optional)

The text under the YAML frontmatter is NOT used by the tailor pipeline directly,
but the matcher's `extract_from_profile_yaml` step does scan it for any skill
mentions that aren't in the structured `skills:` lists above. So if you mention
"PyTorch" or "GraphQL" in narrative form here, those still count toward matches.

Use this section for the kind of free-form intro you'd put on a personal site:
who you are, what kinds of problems you like to solve, what's drawing you toward
new work.
