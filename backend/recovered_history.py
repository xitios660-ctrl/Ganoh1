"""Monthly aggregates transcribed from the 2026-09-28 GANOH report.

The PDF gives these monthly totals, not individual paid orders. Keep them
separate from live orders so debt, cash, and product rankings stay factual.
"""
import os

# month: (revenue cents, paid order count) for each store.
PAID_2026 = {
    'runner': {
        3: (934159, 213), 4: (4493929, 894), 5: (3550115, 701),
        6: (4383425, 437), 7: (4096075, 614), 8: (4111828, 639),
        9: (3431115, 510),
    },
    'gym-londres': {
        3: (496051, 299), 4: (2214637, 1224), 5: (1807685, 981),
        6: (1890355, 599), 7: (1959040, 540), 8: (1869170, 573),
        9: (1648085, 554),
    },
}


def archived_month(year, month, store=None):
    if os.environ.get('GANOH_RECOVERY_SOURCE') != 'pdf' or year != 2026:
        return (0, 0)
    stores = (store,) if store and store != 'all' else PAID_2026
    cents = count = 0
    for entry in stores:
        rev, orders = PAID_2026.get(entry, {}).get(month, (0, 0))
        cents += rev
        count += orders
    return (cents / 100, count)
