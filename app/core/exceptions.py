class VoiceAgentError(Exception):
    status_code: int = 500


class NotFoundError(VoiceAgentError):
    status_code = 404


class UnknownError(NotFoundError):
    status_code = 404


class ValidationError(VoiceAgentError):
    status_code = 422


class UnsupportedProviderError(VoiceAgentError):
    status_code = 400


class OwnershipError(VoiceAgentError):
    status_code = 403


class LLMError(VoiceAgentError):
    status_code = 502


class RateLimitError(LLMError):
    status_code = 429


class RetrievalError(VoiceAgentError):
    status_code = 502


class STTError(VoiceAgentError):
    status_code = 502
