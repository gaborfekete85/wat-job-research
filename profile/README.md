# `profile/` — your CV lives here

This directory is the **single source of truth** for your professional profile.
Every step of the pipeline reads from it:

| File | What it is | Tracked in git? |
|---|---|:---:|
| `profile.md.example` | The starter template. Tracked so new installs always have a reference. | ✅ |
| `profile.md` | Your actual CV in YAML frontmatter + free-text body. | ❌ (gitignored) |
| `cv_source.pdf` | Your existing CV as a PDF — used as the visual template for tailored output (the header with QR codes / photo / contact is overlaid onto every generated CV). | ❌ (gitignored) |

## First-time setup

```bash
cp profile/profile.md.example profile/profile.md   # then edit with your details
# Drop your existing CV PDF in here so the tailor can preserve its header:
cp ~/Downloads/your-cv.pdf profile/cv_source.pdf
```

`profile.md` and `cv_source.pdf` are gitignored by default — your personal CV
never gets pushed to a public fork by accident. If you want your CV to follow
you across machines via your own **private** fork, you can `git add -f` them
intentionally:

```bash
git add -f profile/profile.md profile/cv_source.pdf
```

…but only do that if you know your fork is private.

## Why a dedicated directory

Earlier versions of the project kept these files under `temp/resources/`, which
was confusing — `temp/` reads as "ephemeral / regenerable", but the profile is
neither. The pipeline depends on it for every match score, every tailored CV,
every cover letter. Promoting it to a first-class directory makes that
relationship obvious.
