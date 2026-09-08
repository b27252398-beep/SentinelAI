from app.db.session import SessionLocal
from app.auth.seed import seed_rbac, seed_initial_admin

def main():
    db = SessionLocal()
    try:
        seed_rbac(db)
        seed_initial_admin(db)
    finally:
        db.close()

if __name__ == "__main__":
    main()
