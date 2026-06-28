# Snowflake Bank Platform

End-to-end banking data platform built to demonstrate Snowflake as an
engineering platform (not just analytics): Python ETL, AWS S3 ingestion,
Snowpipe, RBAC, dynamic data masking, monitoring, and CI/CD.

**Status: in progress.** Currently complete: synthetic data generation
(Phase 1 of 8). Architecture and full write-up coming as later phases land.

## Tech stack
Python, Snowflake, AWS S3, Snowpipe, Terraform, GitHub Actions, Streamlit

## Structure
- `python/` — synthetic data generation (customers, accounts, transactions, loans, credit cards, fraud events)
- `data/` — generated CSVs (not committed — run `python/generate_data.py` to produce locally)
