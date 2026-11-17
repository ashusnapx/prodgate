import itertools
import threading


class PaymentDeclined(Exception):
    """The card issuer refused the authorization."""


class PaymentGatewayError(Exception):
    """The processor rejected a capture, void or refund."""


class FakeGateway:
    """In-memory card processor with the real processor's capture, void and refund rules."""

    DECLINE_TOKENS = {"tok_decline", "tok_insufficient_funds"}

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.charges: dict[str, dict] = {}
        self.refunds: list[tuple[str, int]] = []

    def _charge(self, ref: str) -> dict:
        try:
            return self.charges[ref]
        except KeyError:
            raise PaymentGatewayError(f"unknown charge {ref}") from None

    def authorize(self, amount_cents: int, card_token: str) -> str:
        if card_token in self.DECLINE_TOKENS:
            raise PaymentDeclined(card_token.removeprefix("tok_"))
        with self._lock:
            ref = f"ch_{next(self._ids)}"
            self.charges[ref] = {"authorized": amount_cents, "captured": 0, "refunded": 0, "voided": False}
        return ref

    def capture(self, ref: str, amount_cents: int) -> None:
        with self._lock:
            charge = self._charge(ref)
            if charge["voided"]:
                raise PaymentGatewayError("charge was voided")
            if amount_cents > charge["authorized"]:
                raise PaymentGatewayError("capture exceeds authorization")
            charge["captured"] = amount_cents

    def void(self, ref: str) -> None:
        with self._lock:
            charge = self._charge(ref)
            if charge["captured"]:
                raise PaymentGatewayError("captured charges must be refunded, not voided")
            charge["voided"] = True

    def refund(self, ref: str, amount_cents: int) -> str:
        with self._lock:
            charge = self._charge(ref)
            if charge["refunded"] + amount_cents > charge["captured"]:
                raise PaymentGatewayError("refund exceeds captured amount")
            charge["refunded"] += amount_cents
            self.refunds.append((ref, amount_cents))
            return f"re_{next(self._ids)}"
