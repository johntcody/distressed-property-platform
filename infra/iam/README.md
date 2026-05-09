# IAM Role Definitions

Each JSON file in this directory defines an IAM role for one service group.
The structure is a reference document — not directly consumable by any AWS API.
It contains three sections:

- `AssumeRolePolicyDocument` — the trust policy (who can assume the role)
- `InlinePolicy` — the permissions policy attached inline to the role
- `_comment` / `_comment_arns` — documentation fields (not part of AWS APIs)

## Roles

| File | Role Name | Service |
|---|---|---|
| `fastapi-api-role.json` | `dpip-fastapi-api` | All FastAPI services except alert_engine, avm_service |
| `alert-engine-role.json` | `dpip-alert-engine` | alert_engine ECS task |
| `avm-service-role.json` | `dpip-avm-service` | avm_service ECS task |
| `scraper-lambda-role.json` | `dpip-scraper-lambda` | All Lambda scraper functions |
| `cicd-migrations-role.json` | `dpip-cicd-migrations` | CI/CD migration runner |

## How to Apply (AWS CLI)

```bash
ROLE=dpip-fastapi-api
FILE=fastapi-api-role.json

# 1. Create the role (trust policy only)
aws iam create-role \
  --role-name $ROLE \
  --assume-role-policy-document "$(jq '{Version,Statement} | .Statement = [.Statement[]]' infra/iam/$FILE)"

# 2. Attach the inline permissions policy
aws iam put-role-policy \
  --role-name $ROLE \
  --policy-name ${ROLE}-policy \
  --policy-document "$(jq '.InlinePolicy' infra/iam/$FILE)"
```

Repeat for each role file. Before production, replace the wildcard account ID
(`*`) in all ARN strings with your actual AWS account ID:

```bash
aws sts get-caller-identity --query Account --output text
```

## ARN Wildcard Note

All ARNs currently use `*` for the account ID for portability across
dev/staging/prod. **Replace `*` with the literal account ID before production
deployment** — wildcard account IDs are valid IAM policy syntax but weaken the
resource scope.
