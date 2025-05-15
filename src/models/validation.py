from typing import List, Dict, Any
from llama_stack_client.types.shield import Shield
from llama_stack_client.types.run_shield_response import RunShieldResponse
from llama_stack_client.types.shared.safety_violation import SafetyViolation

class KeywordShield(Shield):
    def __init__(self, banned_keywords: List[str]):
        self.banned_keywords = [kw.lower() for kw in banned_keywords]

    async def __call__(self, messages: List[Dict[str, Any]], **kwargs) -> RunShieldResponse:
        content = " ".join(m.get("content", "") for m in messages).lower()

        for keyword in self.banned_keywords:
            if keyword in content:
                return RunShieldResponse(
                    violation=SafetyViolation(
                        violation_level="error",
                        metadata={"matched_keyword": keyword},
                        user_message=f"Your input contains a prohibited keyword: '{keyword}'."
                    )
                )

        return RunShieldResponse(violation=None)