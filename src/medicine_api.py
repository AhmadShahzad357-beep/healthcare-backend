import re
from typing import Dict, List, Optional
from config import OPENFDA_LABEL_URL
try:
    import requests
except ImportError:
    requests = None

INTERACTION_DB = {
    ("aspirin", "warfarin"): {"severity": "High", "message": "Bleeding risk significantly increases."},
    ("paracetamol", "aspirin"): {"severity": "Moderate", "message": "Both are painkillers. May increase stomach irritation."},
    ("paracetamol", "ibuprofen"): {"severity": "Moderate", "message": "Can be taken together but consult doctor."},
    ("ibuprofen", "aspirin"): {"severity": "High", "message": "Combining NSAIDs increases risk of stomach ulcers."},
    ("metformin", "insulin"): {"severity": "Moderate", "message": "May increase risk of hypoglycemia."},
}

def _normalize_drug_name(name: str) -> str:
    name = name.lower().strip()
    synonyms = {
        "panadol": "paracetamol", "acetaminophen": "paracetamol",
        "brufen": "ibuprofen", "advil": "ibuprofen", "motrin": "ibuprofen",
        "disprin": "aspirin", "ecospirin": "aspirin"
    }
    return synonyms.get(name, name)

def check_local_interaction(drug1: str, drug2: str) -> Optional[Dict]:
    d1 = _normalize_drug_name(drug1)
    d2 = _normalize_drug_name(drug2)
    key1, key2 = (d1, d2), (d2, d1)
    return INTERACTION_DB.get(key1) or INTERACTION_DB.get(key2)

def fetch_drug_info_from_openfda(drug_name: str) -> Optional[str]:
    if not requests: return None
    try:
        params = {"search": f"openfda.brand_name:{drug_name}+OR+openfda.generic_name:{drug_name}", "limit": 1}
        response = requests.get(OPENFDA_LABEL_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("results"):
                result = data["results"][0]
                info = []
                if result.get("indications_and_usage"):
                    info.append(f"Indication: {result['indications_and_usage'][0][:200]}...")
                if result.get("warnings"):
                    info.append(f"Warning: {result['warnings'][0][:200]}...")
                if info: return "\n".join(info)
        return None
    except: return None

def check_medicine_interaction(drug1: str, drug2: str) -> Dict:
    result = {"drug1": drug1, "drug2": drug2, "interaction_found": False, "severity": "Unknown", "message": "", "source": "Local DB"}
    local_result = check_local_interaction(drug1, drug2)
    if local_result:
        result["interaction_found"] = True
        result["severity"] = local_result["severity"]
        result["message"] = local_result["message"]
        return result
    d1_info = fetch_drug_info_from_openfda(drug1)
    d2_info = fetch_drug_info_from_openfda(drug2)
    if d1_info or d2_info:
        result["interaction_found"] = False
        result["message"] = f"No known major interaction found.\nInfo about {drug1}: {d1_info or 'Not found'}\nInfo about {drug2}: {d2_info or 'Not found'}"
        result["source"] = "Local DB + OpenFDA"
        return result
    result["message"] = f"No known interaction data found for '{drug1}' and '{drug2}'. Please consult a doctor."
    return result
