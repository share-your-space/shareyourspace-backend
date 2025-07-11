from pydantic import BaseModel
from typing import List, Optional
from datetime import date

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
    date: date
    amount: float
    pdf_url: str

class BillingInfo(BaseModel):
    current_plan: Plan
    payment_method: Optional[PaymentMethod]
    invoices: List[Invoice]
    plan_renewal_date: date
    available_plans: List[Plan]

    class Config:
        orm_mode = True
