from tools.match.extract_skills import extract_from_text, extract_from_profile_yaml

SAMPLE_JD = """
We are looking for a senior backend engineer with strong AWS, Kafka, and Kubernetes
experience. PostgreSQL knowledge required. Bonus: Terraform.
"""

def test_extract_canonical_skills():
    skills = extract_from_text(SAMPLE_JD)
    assert "AWS" in skills
    assert "Kafka" in skills
    assert "Kubernetes" in skills
    assert "PostgreSQL" in skills
    assert "Terraform" in skills

def test_does_not_match_substrings_of_unrelated_words():
    # "Java" should not match "JavaScript"
    skills = extract_from_text("We use JavaScript and TypeScript.")
    assert "JavaScript" in skills
    assert "Java" not in skills

def test_case_insensitive():
    skills = extract_from_text("python and POSTGRES")
    assert "Python" in skills
    assert "PostgreSQL" in skills

def test_profile_extraction_uses_yaml_skills():
    profile_yaml = """
---
skills:
  languages: [Java, Python]
  frameworks: [Spring, Kafka]
  cloud_devops: [AWS, Kubernetes]
---
some long-form text mentioning React.
"""
    skills = extract_from_profile_yaml(profile_yaml)
    assert {"Java", "Python", "Spring", "Kafka", "AWS", "Kubernetes", "React"}.issubset(skills)
