# Dashboard Phase 0 Contract

Phase 0 is the dashboard foundation. It defines the page contract before any business widgets are added.

## Endpoint

`GET /api/dashboard/home/meta/?entity=<entity_id>`

Optional:

- `entityfinid`
- `subentity`
- `as_of_date`
- `from_date`
- `to_date`
- `currency`
- `search`

## Returned sections

- `scope`
- `default_scope`
- `filters`
- `permissions`
- `layout`
- `widget_catalog`
- `role_view_profiles`

## Phase 0 rules

- Only shell widgets are active.
- Planned widgets remain in the registry but stay locked until their phase is reached and the required permissions exist.
- The frontend should use the response as the single source of truth for filter order, layout zones, and widget visibility.

