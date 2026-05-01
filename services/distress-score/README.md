# Distress Score Service

Computes a composite 0–100 distress score for each property based on event signals.

## Scoring Signals

- Foreclosure filing (weight: 0.4)
- Tax delinquency severity (weight: 0.3)
- Pre-foreclosure status (weight: 0.2)
- Probate filing (weight: 0.1)

> TODO: Refine weights with domain expert input.
