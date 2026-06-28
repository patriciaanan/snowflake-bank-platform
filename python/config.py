"""
Configuration for the synthetic banking data generator.

Centralising these numbers here means you can demo a "small" run (fast,
for local dev / CI) or a "full" run (5-10M rows, for the real portfolio
showcase) just by changing SCALE, without touching generator logic.
"""

import os

# ---- Scale control -----------------------------------------------------
# "small"  -> good for local dev / unit testing the pipeline end to end
# "medium" -> good for demoing on your own laptop without running out of RAM
# "full"   -> the 5-10M row showcase scale used in the README
SCALE = os.environ.get("DATA_SCALE", "medium")

SCALE_PROFILES = {
    "small":  {"customers": 1_000,    "accounts_per_customer": (1, 2), "txns_per_account": (5, 20)},
    "medium": {"customers": 50_000,   "accounts_per_customer": (1, 3), "txns_per_account": (20, 150)},
    "full":   {"customers": 500_000,  "accounts_per_customer": (1, 4), "txns_per_account": (50, 400)},
}

PROFILE = SCALE_PROFILES[SCALE]

# ---- Output ----
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "../data")
BATCH_SIZE = 100_000  # rows per CSV chunk - keeps memory bounded at "full" scale

# ---- Business rules / realism knobs ----
ACCOUNT_TYPES = ["savings", "checking", "term_deposit", "offset"]
LOAN_TYPES = ["home_loan", "personal_loan", "auto_loan", "business_loan"]
TXN_TYPES = ["purchase", "withdrawal", "deposit", "transfer", "direct_debit", "fee"]
RISK_SEGMENTS = ["low", "medium", "high"]
RISK_SEGMENT_WEIGHTS = [0.75, 0.20, 0.05]  # most customers are low risk

FRAUD_RATE_BY_RISK = {"low": 0.0008, "medium": 0.004, "high": 0.02}
FRAUD_TYPES = ["card_not_present", "account_takeover", "card_skimming", "phishing_induced", "synthetic_identity"]

LOAN_STATUS_WEIGHTS = {"active": 0.7, "paid_off": 0.2, "default": 0.05, "in_arrears": 0.05}

# Data quality issues injected deliberately - gives you something real to
# clean in the Raw -> Clean schema transformation later (Phase 4)
NULL_EMAIL_RATE = 0.02
INCONSISTENT_PHONE_FORMAT_RATE = 0.15
DUPLICATE_CUSTOMER_RATE = 0.005  # simulates accidental duplicate sign-ups
