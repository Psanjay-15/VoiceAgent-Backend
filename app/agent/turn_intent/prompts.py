TURN_INTENT_PROMPT = (
    "Classify whether the caller's latest utterance is trying to end the voice conversation. "
    "Return only JSON with keys: intent, confidence, reason. intent must be either "
    "continue_conversation or end_conversation. Use end_conversation when the caller clearly "
    "wants to stop, close, wrap up, says goodbye, says they have nothing else, or thanks the "
    "agent in a way that ends the call. Use continue_conversation for normal real estate "
    "questions, corrections, email confirmations, scheduling details, or polite acknowledgements "
    "that do not clearly end the call. confidence must be a number from 0 to 1."
)
