#!/usr/bin/env python3
import argparse
import os
import sys

os.environ.setdefault("SECRET_KEY", "manage-users-cli-no-server-needed")


def cmd_add(args):
    from app.auth import add_user, update_password
    import getpass

    password = args.password or getpass.getpass(f"Password for {args.username}: ")
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    try:
        add_user(args.username, password, args.role)
        print(f"User '{args.username}' added with role '{args.role}'.")
    except ValueError:
        update_password(args.username, password)
        print(f"User '{args.username}' password updated.")


def cmd_delete(args):
    from app.auth import delete_user
    if delete_user(args.username):
        print(f"User '{args.username}' deleted.")
    else:
        print(f"User '{args.username}' not found.", file=sys.stderr)
        sys.exit(1)


def cmd_list(_):
    from app.auth import list_users
    users = list_users()
    if not users:
        print("No users configured.")
        return
    print(f"{'Username':<20} {'Role':<10}")
    print("-" * 30)
    for u in users:
        print(f"{u['username']:<20} {u['role']:<10}")


def cmd_secret(_):
    from app.auth import generate_secret_key
    key = generate_secret_key()
    print(f"Generated SECRET_KEY:\n{key}")
    print("\nAdd this to your .env file:\nSECRET_KEY=" + key)


parser = argparse.ArgumentParser(description="check.health user management")
sub = parser.add_subparsers(dest="command", required=True)

p_add = sub.add_parser("add", help="Add or update a user")
p_add.add_argument("username")
p_add.add_argument("--password", default=None, help="Password (prompted if omitted)")
p_add.add_argument("--role", default="viewer", choices=["admin", "viewer"])

p_del = sub.add_parser("delete", help="Delete a user")
p_del.add_argument("username")

sub.add_parser("list", help="List all users")
sub.add_parser("secret", help="Generate a SECRET_KEY value")

args = parser.parse_args()
{"add": cmd_add, "delete": cmd_delete, "list": cmd_list, "secret": cmd_secret}[args.command](args)
