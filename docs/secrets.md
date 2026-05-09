# Secrets Management

All credentials are stored in AWS Secrets Manager. No passwords, API keys, or
connection strings appear in source code, `.env` files, or deployment configs.

---

## Naming Convention

`dpip/<service-or-resource>/<secret-name>`

| Secret Name | Type | Consumed By | IAM Role |
|---|---|---|---|
| `dpip/db/app_user` | DB connection string (postgres://app_user:…) | All FastAPI services, Lambda scrapers | `dpip-fastapi-services`, `dpip-avm-service`, `dpip-scraper-lambda` |
| `dpip/db/migrations_user` | DB connection string (postgres://migrations_user:…) | CI/CD migration runner only | `dpip-cicd-migrations` |
| `dpip/sqs/alert_queue_url` | SQS queue URL string | Alert engine producer + consumer | `dpip-fastapi-services` |
| `dpip/avm/estated_api_key` | Estated API key string | AVM service only | `dpip-avm-service` |

---

## IAM Roles

Each ECS task and Lambda function assumes a dedicated IAM role. Role definitions
are in [`infra/iam/`](../infra/iam/).

| Role | Policy file | Secrets accessible |
|---|---|---|
| `dpip-fastapi-services` | `fastapi-services-role.json` | `dpip/db/app_user`, `dpip/sqs/alert_queue_url` |
| `dpip-avm-service` | `avm-service-role.json` | `dpip/db/app_user`, `dpip/avm/estated_api_key` |
| `dpip-scraper-lambda` | `scraper-lambda-role.json` | `dpip/db/app_user` |
| `dpip-cicd-migrations` | `cicd-migrations-role.json` | `dpip/db/migrations_user` |

---

## How Secrets Are Fetched

Services import from `services/config.py`:

```python
from services.config import get_db_url, get_sqs_queue_url, get_estated_api_key
```

`get_secret(name)` is backed by `lru_cache` — Secrets Manager is called once at
startup and the value is cached for the lifetime of the process.

**Rotation handling:** AWS Secrets Manager 90-day rotation is enabled on
`dpip/db/app_user` and `dpip/db/migrations_user`. The `boto3` client
automatically retries with the new secret value when rotation is in progress.

---

## Local / CI Development

Set `AWS_SECRETS_MANAGER_ENDPOINT=local` in your environment. In this mode
`get_secret(name)` reads from environment variables instead of Secrets Manager.
The secret name is converted to an env var key by uppercasing and replacing
`/`, `.`, `-` with `_`:

| Secret name | Local env var |
|---|---|
| `dpip/db/app_user` | `DPIP_DB_APP_USER` |
| `dpip/db/migrations_user` | `DPIP_DB_MIGRATIONS_USER` |
| `dpip/sqs/alert_queue_url` | `DPIP_SQS_ALERT_QUEUE_URL` |
| `dpip/avm/estated_api_key` | `DPIP_AVM_ESTATED_API_KEY` |

A `.env.example` file in the repo root documents the local values. Never commit
a `.env` file with real credentials.

---

## Secret Rotation Schedule

| Secret | Rotation period | Who rotates |
|---|---|---|
| `dpip/db/app_user` | 90 days | Secrets Manager automatic rotation |
| `dpip/db/migrations_user` | 90 days | Secrets Manager automatic rotation |
| `dpip/avm/estated_api_key` | Manual (provider-issued) | Platform operator |
| `dpip/sqs/alert_queue_url` | Not applicable (URL, not credential) | — |
