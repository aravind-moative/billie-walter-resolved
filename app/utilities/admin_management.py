import argparse

from app.utilities.database import AdminDatabaseManager


def create_admin_user(email, password, name):
    db = AdminDatabaseManager()
    admin = db.create_admin(email=email, password=password, name=name)
    if admin:
        print(f"Admin user {email} created successfully!")
    else:
        print(f"Failed to create admin user {email}. User might already exist.")


def delete_admin_user(email):
    db = AdminDatabaseManager()
    success = db.delete_admin(email)

    if success:
        print(f"Admin user {email} deleted successfully!")
    else:
        print(f"Admin user {email} not found or deletion failed.")


def list_accounts():
    db = AdminDatabaseManager()
    admins = db.get_all_admins()

    if not admins:
        print("No admin users found in the database.")
        return

    print("\nAdmin Accounts:")
    print("-" * 50)
    for admin in admins:
        print(f"Email: {admin.email}")
        print(f"Name: {admin.name}")
        print(f"Last Login: {admin.last_login}")
        print("-" * 50)


def main():
    parser = argparse.ArgumentParser(description="Admin User Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create admin command
    create_parser = subparsers.add_parser("create", help="Create an admin user")
    create_parser.add_argument("--email", required=True, help="Admin email")
    create_parser.add_argument("--password", required=True, help="Admin password")
    create_parser.add_argument("--name", required=True, help="Admin name")

    # Delete admin command
    delete_parser = subparsers.add_parser("delete", help="Delete an admin user")
    delete_parser.add_argument("--email", required=True, help="Admin email to delete")

    # List accounts command
    subparsers.add_parser("list", help="List all admin accounts")

    args = parser.parse_args()

    if args.command == "create":
        create_admin_user(args.email, args.password, args.name)
    elif args.command == "delete":
        delete_admin_user(args.email)
    elif args.command == "list":
        list_accounts()
    else:
        parser.print_help()


if __name__ == "__main__":
    # python3 app/utilities/admin_management.py create --email "admin@example.com" --password "your_password" --name "Admin Name"
    # python3 app/utilities/admin_management.py delete --email "admin@example.com"
    # python3 app/utilities/admin_management.py list
    main()
