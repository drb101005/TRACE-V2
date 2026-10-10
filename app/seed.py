from datetime import date
from app.core.security import hash_password
from app.db.session import SessionLocal, init_db
from app.models.identity import User, Organization, OrganizationMembership
from app.models.engagement import Engagement, EngagementMembership

DEMO_USERS = [
    ("admin@example.com", "Demo Administrator", "ADMIN"),
    ("client@example.com", "Demo Client Employee", "CLIENT_EMPLOYEE"),
    ("auditor@example.com", "Demo Independent Auditor", "INDEPENDENT_AUDITOR"),
    ("reviewer@example.com", "Demo Human Auditor", "HUMAN_AUDITOR"),
]
DEMO_PASSWORD = "DemoPass123!"

def main():
    init_db()
    db = SessionLocal()
    try:
        users = {}
        for email, name, role in DEMO_USERS:
            user = db.query(User).filter_by(email=email).first()
            if not user:
                user = User(email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD),
                            is_active=True, email_verified=True)
                db.add(user)
                db.flush()
            users[role] = user
        org = db.query(Organization).filter_by(name="Synthetic Manufacturing Demo Co.").first()
        if not org:
            org = Organization(name="Synthetic Manufacturing Demo Co.", is_demo=True)
            db.add(org)
            db.flush()
        for role, user in users.items():
            if not db.query(OrganizationMembership).filter_by(organization_id=org.id, user_id=user.id).first():
                db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=role))
        engagement = db.query(Engagement).filter_by(organization_id=org.id, name="Synthetic FY 2025-26 Revenue Audit").first()
        if not engagement:
            engagement = Engagement(organization_id=org.id, name="Synthetic FY 2025-26 Revenue Audit",
                financial_year="2025-26", period_start=date(2025,4,1), period_end=date(2026,3,31),
                status="DATA_PENDING", is_demo=True, created_by=users["ADMIN"].id)
            db.add(engagement)
            db.flush()
        for role, user in users.items():
            if not db.query(EngagementMembership).filter_by(engagement_id=engagement.id, user_id=user.id).first():
                db.add(EngagementMembership(engagement_id=engagement.id, user_id=user.id, role=role))
        db.commit()
        print("Seed complete. Synthetic demo only.")
        print("Demo organization ID:", org.id)
        print("Demo engagement ID:", engagement.id)
        print("Password for all demo accounts:", DEMO_PASSWORD)
    finally:
        db.close()

if __name__ == "__main__":
    main()
