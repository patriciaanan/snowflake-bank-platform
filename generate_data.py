"""
generate_data.py

Generates synthetic banking data for the Snowflake bank platform project:
customers, accounts, transactions, loans, credit_cards, fraud_events.

Usage:
    DATA_SCALE=small python generate_data.py      # quick local test (~1k customers)
    DATA_SCALE=medium python generate_data.py     # default, ~50k customers
    DATA_SCALE=full python generate_data.py        # showcase scale, ~500k customers

Design notes (worth remembering for interviews):
- Customers are generated first; every other table references customer_id
  or account_id generated here, so referential integrity holds by construction.
- Distributions are skewed deliberately (log-normal transaction amounts,
  weighted risk segments) rather than uniform random, because uniform random
  data doesn't look like anything a real bank would produce.
- A small amount of intentional dirtiness (nulls, inconsistent phone formats,
  duplicate customers) is injected so the Raw -> Clean schema transformation
  in Snowflake (Phase 4) has real problems to solve, not a no-op.
- Writing happens in BATCH_SIZE chunks so memory stays bounded at "full" scale.
"""

import os
import csv
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
from faker import Faker
from tqdm import tqdm

import config as cfg

fake = Faker("en_AU")  # Australian locale: addresses, phone formats, names
random.seed(42)
np.random.seed(42)


def ensure_output_dir():
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)


def random_date_between(start: datetime, end: datetime) -> str:
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return (start + timedelta(seconds=random_seconds)).isoformat()


# -------------------------------------------------------------------------
# CUSTOMERS
# -------------------------------------------------------------------------
def generate_customers():
    """
    Generates the customer base. Returns the list of customer_ids generated
    (kept in memory - at 'full' scale that's 500k strings, ~negligible)
    so downstream generators can reference them without re-reading the CSV.
    """
    path = os.path.join(cfg.OUTPUT_DIR, "customers.csv")
    n = cfg.PROFILE["customers"]
    customer_ids = []

    fieldnames = ["customer_id", "first_name", "last_name", "email", "phone",
                  "dob", "address", "city", "state", "postcode", "risk_segment",
                  "created_at"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for _ in tqdm(range(n), desc="customers"):
            cust_id = str(uuid.uuid4())
            customer_ids.append(cust_id)

            first = fake.first_name()
            last = fake.last_name()

            # Inject deliberate dirtiness: missing emails
            email = None if random.random() < cfg.NULL_EMAIL_RATE else \
                f"{first.lower()}.{last.lower()}{random.randint(1,999)}@{fake.free_email_domain()}"

            # Inconsistent phone formats - some clean, some messy
            if random.random() < cfg.INCONSISTENT_PHONE_FORMAT_RATE:
                phone = fake.numerify("04########")  # no spacing/formatting
            else:
                phone = fake.numerify("04## ### ###")

            dob = fake.date_of_birth(minimum_age=18, maximum_age=90).isoformat()
            risk_segment = np.random.choice(cfg.RISK_SEGMENTS, p=cfg.RISK_SEGMENT_WEIGHTS)
            created_at = random_date_between(datetime(2015, 1, 1), datetime(2026, 6, 1))

            writer.writerow({
                "customer_id": cust_id,
                "first_name": first,
                "last_name": last,
                "email": email,
                "phone": phone,
                "dob": dob,
                "address": fake.street_address(),
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postcode": fake.postcode(),
                "risk_segment": risk_segment,
                "created_at": created_at,
            })

    print(f"customers.csv written -> {n:,} rows")
    return customer_ids


# -------------------------------------------------------------------------
# ACCOUNTS
# -------------------------------------------------------------------------
def generate_accounts(customer_ids):
    path = os.path.join(cfg.OUTPUT_DIR, "accounts.csv")
    lo, hi = cfg.PROFILE["accounts_per_customer"]
    account_ids = []
    account_to_customer = {}

    fieldnames = ["account_id", "customer_id", "account_type", "open_date",
                  "balance", "branch_code", "status"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for cust_id in tqdm(customer_ids, desc="accounts"):
            n_accounts = random.randint(lo, hi)
            for _ in range(n_accounts):
                acc_id = str(uuid.uuid4())
                account_ids.append(acc_id)
                account_to_customer[acc_id] = cust_id

                # Balances are log-normal: most accounts modest, a long tail of large ones
                balance = round(float(np.random.lognormal(mean=8.0, sigma=1.2)), 2)

                writer.writerow({
                    "account_id": acc_id,
                    "customer_id": cust_id,
                    "account_type": random.choice(cfg.ACCOUNT_TYPES),
                    "open_date": random_date_between(datetime(2015, 1, 1), datetime(2026, 6, 1))[:10],
                    "balance": balance,
                    "branch_code": f"BR{random.randint(100,999)}",
                    "status": np.random.choice(["active", "dormant", "closed"], p=[0.85, 0.10, 0.05]),
                })

    print(f"accounts.csv written -> {len(account_ids):,} rows")
    return account_ids, account_to_customer


# -------------------------------------------------------------------------
# TRANSACTIONS  (largest table - written in batches)
# -------------------------------------------------------------------------
def generate_transactions(account_ids):
    path = os.path.join(cfg.OUTPUT_DIR, "transactions.csv")
    lo, hi = cfg.PROFILE["txns_per_account"]
    fieldnames = ["txn_id", "account_id", "txn_type", "amount", "merchant",
                  "txn_timestamp", "channel"]

    total_written = 0
    txn_ids_for_fraud_sampling = []  # we'll sample a subset for fraud linkage

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        batch = []
        for acc_id in tqdm(account_ids, desc="transactions"):
            n_txns = random.randint(lo, hi)
            for _ in range(n_txns):
                txn_id = str(uuid.uuid4())
                txn_type = random.choice(cfg.TXN_TYPES)

                # Most transactions are small, log-normal tail for big ones
                amount = round(float(np.random.lognormal(mean=4.0, sigma=1.5)), 2)
                if txn_type in ("withdrawal", "transfer"):
                    amount = -amount  # outflows recorded as negative

                row = {
                    "txn_id": txn_id,
                    "account_id": acc_id,
                    "txn_type": txn_type,
                    "amount": amount,
                    "merchant": fake.company() if txn_type == "purchase" else None,
                    "txn_timestamp": random_date_between(datetime(2023, 1, 1), datetime(2026, 6, 28)),
                    "channel": random.choice(["app", "card", "branch", "atm", "web"]),
                }
                batch.append(row)

                # Keep a light sample of txn_ids for fraud generation (1 in 50)
                if random.random() < 0.02:
                    txn_ids_for_fraud_sampling.append(txn_id)

                if len(batch) >= cfg.BATCH_SIZE:
                    writer.writerows(batch)
                    total_written += len(batch)
                    batch = []

        if batch:
            writer.writerows(batch)
            total_written += len(batch)

    print(f"transactions.csv written -> {total_written:,} rows")
    return txn_ids_for_fraud_sampling


# -------------------------------------------------------------------------
# LOANS
# -------------------------------------------------------------------------
def generate_loans(customer_ids):
    path = os.path.join(cfg.OUTPUT_DIR, "loans.csv")
    fieldnames = ["loan_id", "customer_id", "loan_type", "principal",
                  "interest_rate", "term_months", "status", "start_date"]

    # Not every customer has a loan - roughly 35% do, some have more than one
    loan_customers = random.sample(customer_ids, k=int(len(customer_ids) * 0.35))

    statuses = list(cfg.LOAN_STATUS_WEIGHTS.keys())
    status_weights = list(cfg.LOAN_STATUS_WEIGHTS.values())

    count = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for cust_id in tqdm(loan_customers, desc="loans"):
            n_loans = np.random.choice([1, 2], p=[0.85, 0.15])
            for _ in range(n_loans):
                loan_type = random.choice(cfg.LOAN_TYPES)
                principal = round(float(np.random.lognormal(
                    mean=12.0 if loan_type == "home_loan" else 9.5, sigma=0.6)), 2)

                writer.writerow({
                    "loan_id": str(uuid.uuid4()),
                    "customer_id": cust_id,
                    "loan_type": loan_type,
                    "principal": principal,
                    "interest_rate": round(random.uniform(4.5, 12.5), 2),
                    "term_months": random.choice([12, 24, 36, 60, 120, 240, 360]),
                    "status": np.random.choice(statuses, p=status_weights),
                    "start_date": random_date_between(datetime(2016, 1, 1), datetime(2026, 1, 1))[:10],
                })
                count += 1

    print(f"loans.csv written -> {count:,} rows")


# -------------------------------------------------------------------------
# CREDIT CARDS
# -------------------------------------------------------------------------
def generate_credit_cards(account_ids, account_to_customer):
    path = os.path.join(cfg.OUTPUT_DIR, "credit_cards.csv")
    fieldnames = ["card_id", "account_id", "card_number_masked", "card_type",
                  "credit_limit", "expiry", "issued_date"]

    # Roughly 40% of accounts have a linked credit card
    card_accounts = random.sample(account_ids, k=int(len(account_ids) * 0.4))

    count = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for acc_id in tqdm(card_accounts, desc="credit_cards"):
            # Store pre-masked - real masking demo happens via Dynamic Data
            # Masking policies on a FULL (unmasked) raw landing table in
            # Snowflake; this masked version simulates what a non-privileged
            # downstream consumer would already see if landed from a vendor feed.
            last4 = random.randint(1000, 9999)
            expiry_year = random.randint(26, 31)

            writer.writerow({
                "card_id": str(uuid.uuid4()),
                "account_id": acc_id,
                "card_number_masked": f"**** **** **** {last4}",
                "card_type": random.choice(["visa_debit", "mastercard_credit", "visa_credit"]),
                "credit_limit": random.choice([1000, 2000, 5000, 10000, 15000, 25000]),
                "expiry": f"{random.randint(1,12):02d}/{expiry_year}",
                "issued_date": random_date_between(datetime(2018, 1, 1), datetime(2026, 1, 1))[:10],
            })
            count += 1

    print(f"credit_cards.csv written -> {count:,} rows")


# -------------------------------------------------------------------------
# FRAUD EVENTS
# -------------------------------------------------------------------------
def generate_fraud_events(txn_id_sample):
    path = os.path.join(cfg.OUTPUT_DIR, "fraud_events.csv")
    fieldnames = ["fraud_id", "txn_id", "fraud_type", "detected_at",
                  "status", "amount_disputed"]

    # Apply an overall ~3% fraud rate across the *sampled* txn pool (recall
    # txn_id_sample is already a 2% sample of all transactions, so this
    # works out to roughly 0.06% of all transactions being fraudulent -
    # realistic, while still leaving enough rows to build dashboards on
    # even at "small" scale. Tune via FRAUD_RATE_BY_RISK if you want it
    # segment-aware later.
    n_fraud = max(20, int(len(txn_id_sample) * 0.03))
    fraud_txns = random.sample(txn_id_sample, k=min(n_fraud, len(txn_id_sample)))

    count = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for txn_id in tqdm(fraud_txns, desc="fraud_events"):
            writer.writerow({
                "fraud_id": str(uuid.uuid4()),
                "txn_id": txn_id,
                "fraud_type": random.choice(cfg.FRAUD_TYPES),
                "detected_at": random_date_between(datetime(2023, 1, 1), datetime(2026, 6, 28)),
                "status": np.random.choice(
                    ["confirmed", "investigating", "false_positive"], p=[0.6, 0.25, 0.15]),
                "amount_disputed": round(float(np.random.lognormal(mean=5.0, sigma=1.3)), 2),
            })
            count += 1

    print(f"fraud_events.csv written -> {count:,} rows")


# -------------------------------------------------------------------------
def main():
    print(f"=== Generating data at scale: {cfg.SCALE} ===")
    ensure_output_dir()

    customer_ids = generate_customers()
    account_ids, account_to_customer = generate_accounts(customer_ids)
    txn_sample = generate_transactions(account_ids)
    generate_loans(customer_ids)
    generate_credit_cards(account_ids, account_to_customer)
    generate_fraud_events(txn_sample)

    print("=== Done. CSVs written to:", os.path.abspath(cfg.OUTPUT_DIR), "===")


if __name__ == "__main__":
    main()
