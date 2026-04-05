class BusinessRuleError(Exception):
    """Base class for domain-level rules that should be surfaced to handlers."""


class CapabilityLockedError(BusinessRuleError):
    """Raised when a feature is not available for the current plan."""


class QuotaExceededError(BusinessRuleError):
    """Raised when an account exceeds a plan limit."""


class ValidationError(BusinessRuleError):
    """Raised when a domain payload is structurally invalid."""


class PaymentIntegrityError(BusinessRuleError):
    """Raised when a billing operation would damage accounting integrity."""
