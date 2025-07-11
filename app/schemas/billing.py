from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime

class Plan(BaseModel):
    name: str
    price: str
    features: List[str]
    is_current: bool

class PaymentMethod(BaseModel):
    card_type: str
    last4: str
    expiry_month: int
    expiry_year: int

class Invoice(BaseModel):
    id: str
    date: datetime
    amount: float
    status: str

class BillingInfo(BaseModel):
    plan: str
    status: str
    next_billing_date: datetime
    payment_method: str
    invoices: List[Invoice]

    class Config:
        orm_mode = True

class SubscriptionUpdate(BaseModel):
    plan: Optional[str] = None
    status: Optional[str] = None

class BillingSettings(BaseModel):
    payment_method: str
    invoice_email: str
