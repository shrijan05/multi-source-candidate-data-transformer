import json
import re
import csv
import argparse
from typing import Dict, Any, List

# --- NORMALIZATION STRATEGIES ---
def normalize_phone(phone: str) -> str:
    """Normalizes phone numbers to basic E.164 format."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}" if digits else ""

def canonicalize_skills(skills: List[str]) -> List[str]:
    """Lowercases, trims, and deduplicates skill strings."""
    return sorted(list(set(s.strip().lower() for s in skills if s.strip())))

# --- STRUCTURED EXTRACTORS ---
def extract_ats_json(filepath: str) -> List[Dict[str, Any]]:
    """Extracts from structured ATS JSON source."""
    extracted = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            for record in data:
                extracted.append({
                    "source": "ats_json",
                    "full_name": record.get("candidateName"),
                    "emails": [record.get("emailAddress")] if record.get("emailAddress") else [],
                    "phones": [record.get("phoneNumber")] if record.get("phoneNumber") else [],
                    "skills": record.get("tags", []),
                    "experience": record.get("workHistory", [])
                })
    except Exception as e:
        print(f"Warning: Failed to process ATS JSON: {e}")
    return extracted

def extract_recruiter_csv(filepath: str) -> List[Dict[str, Any]]:
    """Extracts from structured Recruiter CSV export."""
    extracted = []
    try:
        with open(filepath, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                extracted.append({
                    "source": "recruiter_csv",
                    "full_name": row.get("name"),
                    "emails": [row.get("email")] if row.get("email") else [],
                    "phones": [row.get("phone")] if row.get("phone") else [],
                    "skills": [],
                    "experience": [{
                        "company": row.get("current_company"),
                        "title": row.get("title")
                    }] if row.get("current_company") else []
                })
    except Exception as e:
        print(f"Warning: Failed to process Recruiter CSV: {e}")
    return extracted

# --- UNSTRUCTURED EXTRACTORS ---
def extract_notes_txt(filepath: str) -> List[Dict[str, Any]]:
    """Extracts from unstructured recruiter text notes via regex parsing."""
    extracted = []
    try:
        with open(filepath, 'r') as f:
            text = f.read()
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
            phones = re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
            skills = []
            if "Skills:" in text:
                skills_line = text.split("Skills:")[1].split('\n')[0]
                skills = [s.strip() for s in skills_line.split(',')]
            
            extracted.append({
                "source": "recruiter_notes",
                "emails": emails,
                "phones": phones,
                "skills": skills,
                "experience": []
            })
    except Exception as e:
        print(f"Warning: Failed to process Notes TXT: {e}")
    return extracted

def extract_github_api(filepath: str) -> List[Dict[str, Any]]:
    """Extracts data from the GitHub public profile REST API JSON."""
    extracted = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            # GitHub API provides name, bio, public repos, and languages
            extracted.append({
                "source": "github_api",
                "full_name": data.get("name"),
                "headline": data.get("bio"),
                "skills": data.get("languages", []),
                "emails": [],
                "phones": [],
                "experience": []
            })
    except Exception as e:
        print(f"Warning: Failed to process GitHub API JSON: {e}")
    return extracted

# --- MERGE & PROVENANCE ENGINE ---
def build_canonical_profile(raw_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merges all input streams into a unique canonical record with provenance."""
    profile = {
        "candidate_id": "cand_999",
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": None,
        "links": {},
        "headline": None,
        "years_experience": None,
        "skills": [],
        "experience": [],
        "education": [],
        "provenance": [],
        "overall_confidence": 0.0
    }
    
    confidence_score = 0
    total_sources = len([r for r in raw_records if r])

    for record in raw_records:
        source_name = record["source"]
        
        # Merge Name (Priority: Structured ATS > CSV > Unstructured)
        if record.get("full_name") and not profile["full_name"]:
            profile["full_name"] = record["full_name"]
            profile["provenance"].append({"field": "full_name", "source": source_name, "method": "priority_select"})
            confidence_score += 1

        # Merge Headline
        if record.get("headline") and not profile["headline"]:
            profile["headline"] = record["headline"]
            profile["provenance"].append({"field": "headline", "source": source_name, "method": "api_extraction"})
            
        # Merge Emails
        for email in record.get("emails", []):
            if email not in profile["emails"]:
                profile["emails"].append(email)
                idx = len(profile["emails"]) - 1
                profile["provenance"].append({"field": f"emails[{idx}]", "source": source_name, "method": "merge"})
                confidence_score += 0.5
                
        # Merge Phones
        for phone in record.get("phones", []):
            normalized = normalize_phone(phone)
            if normalized and normalized not in profile["phones"]:
                profile["phones"].append(normalized)
                idx = len(profile["phones"]) - 1
                profile["provenance"].append({"field": f"phones[{idx}]", "source": source_name, "method": "normalize"})
                confidence_score += 0.5
                
        # Merge Skills
        for skill in record.get("skills", []):
            skill_entry = next((s for s in profile["skills"] if s["name"].lower() == skill.lower()), None)
            if skill_entry:
                if source_name not in skill_entry["sources"]:
                    skill_entry["sources"].append(source_name)
                    skill_entry["confidence"] = min(1.0, skill_entry["confidence"] + 0.2)
            else:
                profile["skills"].append({"name": skill, "confidence": 0.7, "sources": [source_name]})
                profile["provenance"].append({"field": "skills", "source": source_name, "method": "aggregated"})

        # Merge Experience
        for exp in record.get("experience", []):
            profile["experience"].append(exp)
            profile["provenance"].append({"field": "experience", "source": source_name, "method": "append"})

    # Normalize final structure
    profile["overall_confidence"] = min(1.0, confidence_score / (total_sources * 1.5 if total_sources else 1))
    return profile

# --- PROJECTION LAYER ---
def resolve_path(data: Dict, path: str) -> Any:
    """Resolves dot-notation / array configuration path rules."""
    try:
        if path.endswith('[0]'):
            key = path.replace('[0]', '')
            return data.get(key, [])[0] if data.get(key) else None
        elif path.endswith('[].name'):
            key = path.replace('[].name', '')
            return [item['name'] for item in data.get(key, [])]
        return data.get(path)
    except Exception:
        return None

def project_profile(canonical_profile: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Projects canonical model into runtime-configured custom format."""
    projected = {}
    
    for field_conf in config.get("fields", []):
        target_path = field_conf["path"]
        source_path = field_conf.get("from", target_path)
        
        value = resolve_path(canonical_profile, source_path)
        
        if not value:
            on_missing = config.get("on_missing", "null")
            if on_missing == "error" and field_conf.get("required", False):
                raise ValueError(f"Required field missing: {target_path}")
            elif on_missing == "omit":
                continue
            else:
                value = None
        
        normalization = field_conf.get("normalize")
        if value and normalization:
            if normalization == "E164":
                value = normalize_phone(value) if isinstance(value, str) else value
            elif normalization == "canonical":
                value = canonicalize_skills(value) if isinstance(value, list) else value
                
        projected[target_path] = value

    if config.get("include_confidence", True):
        projected["provenance"] = canonical_profile["provenance"]
        projected["overall_confidence"] = canonical_profile["overall_confidence"]

    return projected

# --- CLI SURFACE ---
def main():
    parser = argparse.ArgumentParser(description="Multi-Source Data Transformer (2 Structured + 2 Unstructured)")
    parser.add_argument("--ats", default="input_ats.json")
    parser.add_argument("--csv", default="input_recruiter.csv")
    parser.add_argument("--notes", default="input_notes.txt")
    parser.add_argument("--github", default="input_github.json")
    parser.add_argument("--config", required=True)
    parser.add_argument(
    "--output",
    choices=["default", "custom"],
    default="custom",
    help="Choose output schema: default (canonical) or custom (projected)"
)
    
    args = parser.parse_args()
    
    raw_data = []
    raw_data.extend(extract_ats_json(args.ats))
    raw_data.extend(extract_recruiter_csv(args.csv))
    raw_data.extend(extract_notes_txt(args.notes))
    raw_data.extend(extract_github_api(args.github))
    
    canonical = build_canonical_profile(raw_data)

    # ---------------- DEFAULT OUTPUT ----------------
    if args.output == "default":

        # Save default output
        with open("output_default.json", "w") as f:
            json.dump(canonical, f, indent=2)

        # Print default output
        print(json.dumps(canonical, indent=2))

    # ---------------- CUSTOM OUTPUT ----------------
    else:

        with open(args.config, "r") as f:
            runtime_config = json.load(f)

        try:
            final_output = project_profile(canonical, runtime_config)

            # Save custom output
            with open("output_custom.json", "w") as f:
                json.dump(final_output, f, indent=2)

            # Print custom output
            print(json.dumps(final_output, indent=2))

        except ValueError as e:
            print(json.dumps({"error": str(e)}, indent=2))

if __name__ == "__main__":
    main()