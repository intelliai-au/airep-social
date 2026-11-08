# The year, month by month

Copied from the plan doc (AIREP Organic Social Plan, 2026-11-03, revised 2026-11-08) so
that a headless authoring run needs no access to the doc. Change the plan there first,
then here. `author.py` reads this file to brief each writing and filming run.

Each month has one theme that the Tuesday features, the Wednesday Field Notes and the
Thursday posts all serve, timed to the Australian business calendar. "Films" names the
two videos that month's video Tuesdays use: existing ones live in `site/video/`
already; new ones are made by the film run on the third Sunday two months earlier.

| Month | Theme | Films (2 a month) | Dated hooks |
| --- | --- | --- | --- |
| 2026-11 | Stock before the Christmas shutdown: reorder points, lead times, MOQ, supplier POs | `airep_reorder_music.mp4`, `airep_no_ui_po_music.mp4` (existing) | Supplier Christmas cut-offs; first Shipped this month |
| 2026-12 | Get paid before the break: quote to invoice, payments, aged receivables, statements | `airep_quote_to_invoice_music.mp4`, `airep_payment_music.mp4` (existing) | Christmas shutdown date post; Tuesday-only from 22 Dec |
| 2027-01 | One system, no spreadsheets: every module included, CRM and pipeline | `airep_modules_music.mp4`, `airep_no_ui_stage_music.mp4` (existing) | New-year reset; BAS Q2 one month out |
| 2027-02 | BAS and the bank: bank feeds, reconciliation, GST control, supplier bills | Bank-feed reconciliation; supplier bill three-way match (new) | BAS Q2 due 28 Feb |
| 2027-03 | Manufacturing: production orders, bill of materials, QC, the workshop tablet | Production order from BOM to QC; workshop schedule on the tablet (new) | Shipped this month |
| 2027-04 | Shipping and freight: carrier quotes from item dimensions, dispatch | Freight quotes from a sales order; dispatch and labels (new) | BAS Q3 due 28 Apr; Easter 2 to 5 Apr |
| 2027-05 | Workforce: timesheets, pay calendar, timesheet seats at $25 | Timesheet to pay run; the phone app clock-on (new) | Federal Budget week |
| 2027-06 | EOFY: stocktake, write-offs, asset records, the 7-year records test | Stocktake; aged receivables and statements run (new) | EOFY 30 Jun; stocktake date post |
| 2027-07 | New financial year and price certainty: CPI + 3% in writing, no July re-pricing | Morning briefing; customer statements and ageing (new) | STP finalisation 14 Jul; BAS Q4 due 28 Jul |
| 2027-08 | Nova does the retyping: email to sales order, chat-driven approvals | Email to sales order; reorder approved from chat (new) | Shipped this month |
| 2027-09 | Reporting and customer accounts: dashboards, ageing, the customer portal | Reports and dashboards; customer portal (new) | Shipped this month |
| 2027-10 | Projects, tasks and tenders, plus the year-one review | Projects and tasks; tenders (new) | BAS Q1 due 28 Oct; plan refresh queued for year two |
| 2027-11 | The first ten days repeat the three best-performing posts of the year by Buffer metrics | none | Plan for year two takes over |

## Formats and their yearly share

| Slot | Format | Posts a year |
| --- | --- | --- |
| Wednesday | `field_note`: one AU compliance or operations fact as a card | 52 |
| Tuesday | `feature` image: one feature, a mock of its real screen data | 28 |
| Tuesday | `feature` film: a 4:5 compositor film of one job, twice a month | 24 |
| Thursday | `pain`: the spreadsheet pile, the double entry, the whiteboard | 20 |
| Thursday | `price`: CPI + 3% cap, every module included, seat prices | 12 |
| Thursday | `shipped`: three real changes from the airep git log, dated | 12 |
| Thursday | `date_post`: one date, one action (BAS, STP, shutdown, stocktake) | 8 |

The Thursday mix inside a month: `shipped` on the last Thursday, a `date_post` in any
month with a dated hook, `price` once a month, `pain` on the rest.
