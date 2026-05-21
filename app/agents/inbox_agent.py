"""
Inbox Agent — classifies incoming replies and suggests next actions.
"""
import json
import re
from ..services.ai_service import AIService

SYSTEM = """You are a B2B sales assistant who analyzes email replies.
Classify the reply and suggest the best next action.
Always respond with valid JSON only."""


class InboxAgent:
    name = "Inbox Agent"

    REPLY_TYPES = {
        "positive":  "👍 Interested — follow up immediately",
        "negative":  "❌ Not interested — mark as Lost",
        "neutral":   "🤔 Neutral — send more info",
        "ooo":       "🏖️ Out of office — retry in 2 weeks",
        "referral":  "📨 Referred to someone else — add new contact",
        "question":  "❓ Has a question — answer it",
    }

    def __init__(self, ai: AIService):
        self.ai = ai

    def classify_reply(self, reply_text: str, original_email: str = "") -> dict:
        """
        Classify a reply email and recommend the next action.
        Returns: {type, sentiment, next_action, suggested_response, urgency}
        """
        prompt = f"""Analyze this email reply from a B2B prospect:

ORIGINAL EMAIL (we sent):
{original_email[:400] if original_email else 'Not provided'}

REPLY RECEIVED:
{reply_text[:600]}

Classify and return JSON:
{{
  "type": "positive|negative|neutral|ooo|referral|question",
  "sentiment": "positive|negative|neutral",
  "next_action": "specific action to take",
  "suggested_response": "short reply we should send (2-3 sentences)",
  "urgency": "low|medium|high",
  "key_points": ["extracted key point 1", "key point 2"]
}}"""

        raw    = self.ai.generate(prompt, system=SYSTEM)
        result = self._parse(raw)
        result["type_label"] = self.REPLY_TYPES.get(result.get("type", "neutral"),
                                                      "• Unknown — review manually")
        return result

    def bulk_classify(self, replies: list[dict]) -> list[dict]:
        """Classify multiple replies."""
        return [
            {**r, "classification": self.classify_reply(r.get("body", ""), r.get("original", ""))}
            for r in replies
        ]

    def generate_response(self, reply_text: str, classification: dict,
                           contact_name: str, company_name: str) -> str:
        """Generate an appropriate response to a classified reply."""
        reply_type = classification.get("type", "neutral")

        if reply_type == "negative":
            return (f"Hi {contact_name},\n\nThank you for letting me know! "
                    f"I completely understand. I'll reach back out in a few months in case timing changes.\n\n"
                    f"Wishing {company_name} continued success!\n\nBest,\nBraveAspire Team")

        prompt = f"""Write a short reply (3-4 sentences) to this {reply_type} response from {contact_name} at {company_name}.

Their reply: {reply_text[:300]}
Suggested action: {classification.get('next_action', '')}

Keep it conversational and professional. Don't be pushy."""

        return self.ai.generate(prompt)

    def _parse(self, text: str) -> dict:
        text = re.sub(r"```(?:json)?", "", text).strip()
        try:
            d = json.loads(text)
            return d if isinstance(d, dict) else {}
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return {"type": "neutral", "sentiment": "neutral",
                "next_action": "Review manually", "suggested_response": "",
                "urgency": "medium", "key_points": []}
