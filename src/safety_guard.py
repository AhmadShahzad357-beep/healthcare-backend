import re

class SafetyGuard:
    def __init__(self):
        pass

    def check_hallucination(self, response: str, context: str) -> bool:
        dont_know = ["mujhe nahi pata", "i don't know", "not found", "no information"]
        if any(phrase in response.lower() for phrase in dont_know):
            return True
        if "source:" in response.lower() or "medlineplus" in response.lower():
            return True
        if "no relevant information" in context.lower() or not context.strip():
            return False
        return True
