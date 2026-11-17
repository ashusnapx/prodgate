import itertools
from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """The provider could not be reached or refused the call."""


@dataclass
class Charge:
    id: str
    status: str  # "succeeded", "processing" or "failed"
    amount_cents: int
    failure_reason: str | None = None


@dataclass
class ProviderRefund:
    id: str
    charge_id: str
    amount_cents: int


class PaymentProvider(Protocol):
    def create_charge(self, amount_cents: int, idempotency_key: str, metadata: dict) -> Charge: ...
    def get_charge(self, charge_id: str) -> Charge: ...
    def refund(self, charge_id: str, amount_cents: int) -> ProviderRefund: ...


@dataclass
class FakeProvider:
    """In-memory provider for local runs and tests; production wires in the card processor's adapter.

    Set `outcome` to choose what the next charge does.
    """

    outcome: str = "succeeded"
    unreachable: bool = False
    charges: dict[str, Charge] = field(default_factory=dict)
    refunds: list[ProviderRefund] = field(default_factory=list)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    def create_charge(self, amount_cents: int, idempotency_key: str, metadata: dict) -> Charge:
        if self.unreachable:
            raise ProviderError("timed out")
        charge = Charge(id=f"ch_{next(self._ids)}", status=self.outcome, amount_cents=amount_cents)
        if self.outcome == "failed":
            charge.failure_reason = "card_declined"
        self.charges[charge.id] = charge
        return charge

    def get_charge(self, charge_id: str) -> Charge:
        if self.unreachable:
            raise ProviderError("timed out")
        return self.charges[charge_id]

    def refund(self, charge_id: str, amount_cents: int) -> ProviderRefund:
        if self.unreachable:
            raise ProviderError("timed out")
        refund = ProviderRefund(id=f"re_{next(self._ids)}", charge_id=charge_id, amount_cents=amount_cents)
        self.refunds.append(refund)
        return refund
