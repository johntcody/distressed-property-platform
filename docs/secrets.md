# Secrets Management

All credentials are stored in AWS Secrets Manager. No passwords, API keys, or
connection strings appear in source code, `.env` files, or deployment configs.

---

## Naming Convention

`dpip/<service-or-resource>/<secret-name>`

| Secret Name | Type | Consumed By | IAM Role |
|---|---|---|---|
| `dpip/db/app_user` | DB connection string (postgres://app_user:…) | All FastAPI services, Lambda scrapers | `dpip-fastapi-api`, `dpip-alert-engine`, `dpip-avm-service`, `dpip-scraper-lambda` |
| `dpip/db/migrations_user` | DB connection string (postgres://migrations_user:…) | CI/CD migration runner only | `dpip-cicd-migrations` |
| `dpip/sqs/alert_queue_url` | SQS queue URL string | Alert engine only | `dpip-alert-engine` |
| `dpip/avm/attom_api_key` | ATTOM Data API key string | AVM service only | `dpip-avm-service` |

---

## IAM Roles

Each service or service group assumes a least-privilege IAM role scoped to
only the secrets it needs. Role definitions are in [`infra/iam/`](../infra/iam/).

| Role | Policy file | Secrets accessible | Used by |
|---|---|---|---|
| `dpip-fastapi-api` | `fastapi-api-role.json` | `dpip/db/app_user` | All FastAPI services except alert_engine and avm_service |
| `dpip-alert-engine` | `alert-engine-role.json` | `dpip/db/app_user`, `dpip/sqs/alert_queue_url` | alert_engine ECS task only |
| `dpip-avm-service` | `avm-service-role.json` | `dpip/db/app_user`, `dpip/avm/attom_api_key` | avm_service ECS task only |
| `dpip-scraper-lambda` | `scraper-lambda-role.json` | `dpip/db/app_user` | All Lambda scraper functions |
| `dpip-cicd-migrations` | `cicd-migrations-role.json` | `dpip/db/migrations_user` | CI/CD migration runner only |

---

## How Secrets Are Fetched

Services import from `services/config.py`:

```python
from services.config import get_db_url, get_sqs_queue_url, get_attom_api_key
```

`get_secret()` separates local and production paths:

- **Local mode** (`AWS_SECRETS_MANAGER_ENDPOINT=local`): reads env vars directly,
  never cached — env var changes take effect immediately (useful in tests).
- **Production mode**: calls Secrets Manager once via `_get_secret_remote()`,
  result cached for the lifetime of the process via `lru_cache`.

**Rotation handling:** Secret rotation takes effect on the next ECS task restart
or Lambda cold start. The in-process cache is not invalidated mid-run. To pick
up a rotated secret without redeployment, restart the ECS task or invoke a new
Lambda instance.

---

## How to Apply IAM Roles

The JSON files in `infra/iam/` are reference documents, not directly consumable
by any AWS API. Apply them using the AWS CLI:

```bash
# 1. Create the role with the trust policy
aws iam create-role \
  --role-name dpip-fastapi-api \
  --assume-role-policy-document file://infra/iam/fastapi-api-role.json

# 2. Attach the inline policy (extract the InlinePolicy block)
aws iam put-role-policy \
  --role-name dpip-fastapi-api \
  --policy-name dpip-fastapi-api-policy \
  --policy-document file://infra/iam/fastapi-api-inline-policy.json
```

Before production deployment, replace the wildcard account ID (`*`) in all ARNs
with the literal AWS account ID (`aws sts get-caller-identity --query Account`).

---

## Local / CI Development

Set `AWS_SECRETS_MANAGER_ENDPOINT=local` in your environment. In this mode
`get_secret(name)` reads from environment variables instead of Secrets Manager.
The secret name is converted to an env var key by replacing all `/`, `.`, and
`-` characters with `_` and uppercasing the result:

| Secret name | Local env var |
|---|---|
| `dpip/db/app_user` | `DPIP_DB_APP_USER` |
| `dpip/db/migrations_user` | `DPIP_DB_MIGRATIONS_USER` |
| `dpip/sqs/alert_queue_url` | `DPIP_SQS_ALERT_QUEUE_URL` |
| `dpip/avm/attom_api_key` | `DPIP_AVM_ATTOM_API_KEY` |

See `.env.example` in the repo root for a full local setup template.
Never commit a `.env` file with real credentials.

---

## Secret Rotation Schedule

| Secret | Rotation period | Who rotates |
|---|---|---|
| `dpip/db/app_user` | 90 days | Secrets Manager automatic rotation |
| `dpip/db/migrations_user` | 90 days | Secrets Manager automatic rotation |
| `dpip/avm/attom_api_key` | Manual (provider-issued) | Platform operator |
| `dpip/sqs/alert_queue_url` | Not applicable (URL, not credential) | — |
