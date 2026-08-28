from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import uuid4


class StorePaymentError(RuntimeError):
    pass


@dataclass
class PaymentResult:
    status: str
    provider: str
    reference: str | None = None
    metadata: dict | None = None


class StorePaymentProvider(ABC):
    name: str

    @abstractmethod
    def charge(self, *, order_id: str, amount_minor: int, currency: str) -> PaymentResult:
        raise NotImplementedError

    def status(self) -> dict:
        return {"id": self.name, "ready": True}


class MockStorePaymentProvider(StorePaymentProvider):
    """Local-development checkout simulator.

    It never contacts a payment processor and must not be represented as real
    money collection. Paid mock checkout can be disabled by setting
    GAME_CREATER_ALLOW_MOCK_PAID=0.
    """

    name = "mock"

    def __init__(self) -> None:
        self.allow_paid = os.getenv("GAME_CREATER_ALLOW_MOCK_PAID", "1").strip() not in {"0", "false", "False"}

    def charge(self, *, order_id: str, amount_minor: int, currency: str) -> PaymentResult:
        if amount_minor > 0 and not self.allow_paid:
            raise StorePaymentError(
                "Paid mock checkout is disabled. Configure a real payment provider or set GAME_CREATER_ALLOW_MOCK_PAID=1 for local simulation."
            )
        return PaymentResult(
            status="paid",
            provider=self.name,
            reference=f"mock_{uuid4().hex[:16]}",
            metadata={
                "simulated": True,
                "amount_minor": amount_minor,
                "currency": currency,
                "order_id": order_id,
            },
        )

    def status(self) -> dict:
        return {
            "id": self.name,
            "ready": True,
            "simulated": True,
            "paid_simulation_enabled": self.allow_paid,
        }


class StorePaymentRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, StorePaymentProvider] = {
            "mock": MockStorePaymentProvider(),
        }

    def get(self, name: str) -> StorePaymentProvider:
        provider = self.providers.get(name.strip().lower())
        if provider is None:
            raise StorePaymentError(
                f"Unsupported payment provider {name!r}. Available: {', '.join(sorted(self.providers))}"
            )
        return provider

    def catalog(self) -> list[dict]:
        return [provider.status() for provider in self.providers.values()]
