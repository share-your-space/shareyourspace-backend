from datetime import date, timedelta
from app.schemas.billing import BillingInfo, Plan, PaymentMethod, Invoice

def get_billing_info(company_id: int) -> BillingInfo:
    """
    Retrieves billing information for a company.
    This is a mock implementation and should be replaced with actual data retrieval logic.
    """
    # Mock data - in a real application, this would come from a database or payment provider API
    available_plans = [
        Plan(
            name='Community',
            price='Free',
            features=['Up to 10 members', 'Basic analytics', 'Community support'],
            is_current=False
        ),
        Plan(
            name='Pro',
            price='$49/month',
            features=['Up to 50 members', 'Advanced analytics', 'Priority support', 'Custom branding'],
            is_current=True
        ),
        Plan(
            name='Enterprise',
            price='Contact Us',
            features=['Unlimited members', 'Dedicated account manager', 'Premium support & SLA', 'Advanced security & compliance'],
            is_current=False
        ),
    ]

    current_plan = next((plan for plan in available_plans if plan.is_current), available_plans[1])

    payment_method = PaymentMethod(
        card_type='Visa',
        last4='1234',
        expiry_month=12,
        expiry_year=2026
    )

    invoices = [
        Invoice(id='INV-2024-003', date=date(2024, 7, 1), amount=49.00, pdf_url='/invoices/INV-2024-003.pdf'),
        Invoice(id='INV-2024-002', date=date(2024, 6, 1), amount=49.00, pdf_url='/invoices/INV-2024-002.pdf'),
        Invoice(id='INV-2024-001', date=date(2024, 5, 1), amount=49.00, pdf_url='/invoices/INV-2024-001.pdf'),
    ]

    plan_renewal_date = date.today() + timedelta(days=30)

    return BillingInfo(
        current_plan=current_plan,
        payment_method=payment_method,
        invoices=invoices,
        plan_renewal_date=plan_renewal_date,
        available_plans=available_plans
    )
