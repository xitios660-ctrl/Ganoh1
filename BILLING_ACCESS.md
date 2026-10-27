# Temporary billing access

Service: ganoh1, https://ganoh1-tbmo.onrender.com
Render workspace: Mary's workspace (tea-datr84navr4c73elaf40)
Service ID: srv-datrcju0tbcc73f02qrg

Settings (merge changes; never replace other environment variables):
- GANOH_SERVICE_SUSPENDED=true with no valid future GANOH_GRACE_UNTIL: full suspension.
- GANOH_SERVICE_SUSPENDED=true with GANOH_GRACE_UNTIL=<absolute UTC ISO timestamp>: orders and kitchen until that instant; manager, financial totals, history, reports, WhatsApp and financial APIs blocked. Operational order responses omit monetary fields. Customer menu prices and cart amounts remain available for ordering.
- GANOH_SERVICE_SUSPENDED=false: normal access; grace deadline ignored. Only do this when user requests full reactivation.

Deadline must be stored as a fixed timestamp, never computed as now+24h at process startup. Every HTTP request checks the deadline. The frontend uses server time and unmounts the operational interface at expiry. The supervisor stops the operational server at expiry and starts a standalone suspension page. Restarting after expiry cannot start the business app.

No credentials, MongoDB settings or business records are changed by the billing gate. During grace, skip historical repair/recovery jobs, account password rotation, scheduled changes and automatic archival of old orders. Normal requested order/kitchen operations still save changes as usual. Re-enabling full access restores legacy startup behavior: review existing repair hooks/one-shot flags before doing so.

Service-worker caching is network-only to prevent stale cached financial pages/responses. Do not delete pending orders in localStorage or IndexedDB. Previously copied/displayed data cannot be revoked retroactively.

Render's update_environment_variables tool triggers deployment automatically. Capture the deploy ID and verify live status, /api/billing/status, operational endpoints and blocked financial endpoints. Never test writes against real records just to verify the gate.

Validation: python -m unittest discover -s backend/tests -p test_billing_access.py -v; production frontend build; browser countdown/manager/kitchen/expiry checks using mocked data.
