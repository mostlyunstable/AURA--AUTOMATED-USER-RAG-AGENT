# ADR 002: Mandatory PostgreSQL for Integration Tests

## Context
Previously, integration tests would silently fall back to an in-memory SQLite database if PostgreSQL (asyncpg) was unavailable. This meant some database-specific locking, JSON constraints, or syntax issues wouldn't be caught locally.

## Decision
Integration tests MUST use PostgreSQL. Silent fallback to SQLite is removed. If the test cannot connect to PostgreSQL, it fails immediately. 

## Consequences
- CI and local testing guarantees full fidelity with the production database behavior.
- Developers must run `docker compose up db` (or equivalent) to run the test suite.
