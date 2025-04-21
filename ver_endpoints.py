# C:\Users\Vladimir\Documents\Sistema tickets\ver_endpoints.py

from app import create_app

app = create_app()

print("📋 Endpoints registrados:\n")

with app.app_context():
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods))
        print(f"{rule.endpoint:30s} | {methods:20s} | {rule.rule}")
