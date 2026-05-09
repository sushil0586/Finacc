# Entity GST Operating Model

## Purpose

This document defines the current operating rule for entity GST, subentity GST, and compliance credentials in Finacc.

It is intentionally simple:

- one active GST registration per entity
- compliance credentials derive from that entity GST
- subentity GST remains available for future branch-wise GST selection

## Current Rule

For the current production model:

- an entity can have only **one active GST registration**
- that GST registration is the **operational seller GST**
- compliance credentials must align to the same GSTIN
- branch GST can be stored, but it does **not** currently drive seller GST selection

In API and shell context this is represented as:

- `gstno`: current entity GST
- `seller_gstin`: GSTIN actively used by operations
- `gst_selection_mode = entity_primary`

## Single Source Of Truth

### Entity

Entity is the legal business master.

Entity owns:

- legal name
- PAN
- TAN and other statutory identifiers
- active entity GST registration

### Subentity

Subentity is the branch or operational place of business.

Subentity owns:

- branch name
- branch address
- head office / branch identity
- optional branch GST data for future scoped GST use

### Compliance Credentials

Compliance credentials are access credentials only.

They own:

- environment
- service scope
- client key
- client secret
- GST username
- GST password

They do **not** own GST identity.

Credential GSTIN is derived from the active entity GSTIN.

## Why This Rule Exists

The data model is capable of supporting multiple GST registrations, but many runtime flows still operate with an entity-primary GST selection model.

Today, the safest operating contract is:

- one active GST per entity
- explicit visibility of that GST in the shell/context
- no ambiguity between legal GST identity and provider credentials

This keeps onboarding, compliance setup, and sales compliance flows predictable.

## What Users Should Do

### When creating or updating an entity

1. enter the legal business details
2. enter one active entity GSTIN
3. keep PAN/statutory IDs aligned to the same business
4. configure compliance credentials under the entity

### When creating branches

1. create the head office first
2. add branches only when they are operationally needed
3. if branch GST data is known, it may be stored
4. do not assume branch GST becomes seller GST automatically

### When configuring compliance credentials

1. choose environment: sandbox or production
2. choose service scope: e-invoice / e-way / other supported scope
3. enter client key, secret, GST username, password
4. do not retype GST identity as a separate truth

## Sandbox Rule

Sandbox is a special case.

- sandbox provider GSTIN may be a pseudo/test GSTIN
- production legal GSTIN and sandbox credential GSTIN may differ during testing
- this is allowed only for sandbox workflows
- sandbox values must not be treated as production master truth

If a sandbox credential is used:

- keep the environment clearly marked as sandbox
- avoid treating the sandbox GSTIN as a second production entity GST

## Admin Review Checklist

Before enabling compliance operations for an entity, confirm:

1. only one entity GST registration is active
2. the active GST row is marked primary
3. compliance credential GSTIN matches the intended active entity GSTIN for the current environment
4. head office exists
5. branch data is present only where operationally needed

## Support Troubleshooting Checklist

When a GST or IRN issue is reported, check in this order:

1. which entity is selected
2. what `seller_gstin` is in current context
3. whether `gst_selection_mode` is `entity_primary`
4. whether the active entity GST row is correct
5. whether compliance credentials belong to the same environment and GST context
6. whether the issue is sandbox-only or production

## Future Scalable Model

The current rule is intentionally transitional.

The future target model should be:

1. if selected subentity has an active GST registration, use subentity GST
2. otherwise fall back to entity primary GST
3. compliance credentials must match the GSTIN actually being used

That future model is compatible with the current structure because:

- entity GST registrations already exist
- subentity GST registrations already exist
- context now exposes the active GST source explicitly

## Final Decision

Until subentity-first GST selection is fully implemented, Finacc should be operated as:

- **one active GST registration per entity**
- **credentials derived from entity GST**
- **branch GST stored for future scope-aware rollout**

