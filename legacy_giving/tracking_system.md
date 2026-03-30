# Legacy Giving — Tracking & Measurement System

**Owner:** Val (NXT) + Tiffany (relationships)
**Review Cadence:** Monthly pipeline review; annual full audit

---

## What to Track

### 1. Donors (Society Members)
| Data Point | Where Tracked | How |
|------------|--------------|-----|
| Member status | NXT Constituent Code | `Legacy Society Member` |
| Join date | NXT Attribute | `Legacy Society Join Date` |
| Gift type | NXT Attribute | `Legacy Intent Type` |
| Estimated value | NXT Attribute | `Estimated Gift Range` |
| Recognition preference | NXT Attribute | `Recognition Preference` |
| Relationship manager | NXT Attribute | `Relationship Manager` |

### 2. Conversations (Pipeline)
| Data Point | Where Tracked | How |
|------------|--------------|-----|
| Prospect status | NXT Constituent Code | `Legacy Society Prospect` |
| Last conversation date | NXT Action | `Legacy – Initial Conversation` |
| Next scheduled touchpoint | NXT Action (future-dated) | Any legacy action type |
| Conversation notes | NXT Notes on Action | Free text |

### 3. Outcomes
| Data Point | Where Tracked | How |
|------------|--------------|-----|
| Confirmed pledges (year) | NXT Query + manual log | Pull `Legacy – Confirmed Pledge` actions |
| Estimated pipeline value | NXT Attribute summary | Pull `Estimated Gift Range` across all members |
| Realized gifts | NXT Gift record | Standard gift entry; tag to Legacy fund |
| Stewardship completion | NXT Query | Actions logged vs. members requiring annual touchpoint |

---

## NXT Reports to Run Regularly

| Report Name | Frequency | Purpose |
|-------------|-----------|---------|
| `Legacy Society – Active Members` | Monthly | Know who's in the Society |
| `Legacy Society – Stewardship Due` | Monthly | Members with no touchpoint in 12+ months |
| `Legacy Society – Prospects` | Monthly | Pipeline health check |
| `Legacy Society – Annual Report List` | Annually (Q3) | Pull consent list for print |
| `Legacy Pipeline Value Summary` | Quarterly | Leadership/board reporting |

---

## Key Metrics to Report to Leadership

| Metric | Target (Year 1) | Notes |
|--------|----------------|-------|
| Total Society members | 10–20 | Realistic for launch year |
| New members added | Track monthly | — |
| Prospects in active cultivation | 20–30 | — |
| Conversations initiated (year) | 50+ | Including Salon attendees |
| Estimated pipeline value | — | Track range, not exact |
| Stewardship completion rate | 100% | Annual touchpoint for all members |
| Donor retention (year-over-year) | 100% | Legacy donors should never lapse |

---

## Conversation Tracking (Tiffany's Log)

In addition to NXT actions, maintain a simple working document for weekly pipeline management:

### Weekly Pipeline Log (Template)

```
Week of: ___________

NEW CONVERSATIONS:
- [Name] — [Date] — [Summary] — [Next step]

FOLLOW-UPS DUE:
- [Name] — [Due date] — [Action needed]

CONFIRMATIONS THIS WEEK:
- [Name] — [Date confirmed] — [Form submitted? Y/N]

SOCIETY UPDATES:
- [Any changes to recognition pref, gift type, contact info]
```

---

## Annual Review Checklist

Run each January:

- [ ] Pull full `Legacy Society – Active Members` report
- [ ] Confirm all members have had a touchpoint in the last 12 months
- [ ] Update estimated gift ranges if new info is available
- [ ] Confirm recognition preferences ahead of Annual Report print
- [ ] Review prospects — who moved forward? Who needs re-engagement?
- [ ] Report pipeline value to Development Director and CEO
- [ ] Schedule stewardship touchpoints for all members (future-date in NXT)
- [ ] Plan Legacy Salon dates for the coming year

---

## Realized Gift Process (When Estate Contacts TMM)

| Step | Action | Owner |
|------|--------|-------|
| 1 | Estate notification received | Val |
| 2 | Notify Development Director + CEO immediately | Val |
| 3 | Update NXT: `Legacy Society – Deceased` + `Legacy – Estate Notification` action | Val |
| 4 | Acknowledge family with personal letter (from David) | Val drafts, David signs |
| 5 | Work with legal/finance to process gift | Leadership |
| 6 | Enter gift in NXT gift record tagged to Legacy fund | Val |
| 7 | Recognize in Annual Report + any appropriate public acknowledgment | Comms |

---

## Definition of Success (Year 1)

- At least 10 confirmed Golden Heart Legacy Society members
- 100% of members have received a welcome call and letter
- 100% of members have had at least one annual stewardship touchpoint
- First Legacy Salon hosted with positive donor feedback
- Legacy giving page live on website
- Internal policy approved by board/committee
- FreeWill (or equivalent) integrated into website and email CTAs
