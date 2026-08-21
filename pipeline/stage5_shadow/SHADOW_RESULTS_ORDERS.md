# Live shadow-mode results — ORDERS (Oracle Forms legacy vs migrated .NET)

Each operation ran through TWO independent paths against the SAME schema:

- **Legacy**: the exact PL/SQL the re-authored form's triggers execute (direct DML with the line-freeze/stock DB triggers firing, plus `pkg_pricing` / `pkg_orders` calls), executed **by Oracle** via sqlplus.
- **Modern**: the live migrated .NET `OrdersController` over HTTPS (CloudFront -> ALB -> ECS Fargate).

| Case | Legacy (Oracle) | Modern (.NET) | Verdict |
|---|---|---|---|
| price product 1 | 27 | 27 | ✅ match |
| price product 2 | 34 | 34 | ✅ match |
| price product 3 | 41 | 41 | ✅ match |
| price product 4 | 48 | 48 | ✅ match |
| price product 5 | 55 | 55 | ✅ match |
| price product 6 | 22 | 22 | ✅ match |
| price product 7 | 29 | 29 | ✅ match |
| price product 8 | 36 | 36 | ✅ match |
| price product 9 | 43 | 43 | ✅ match |
| price product 10 | 50 | 50 | ✅ match |
| price product 11 | 57 | 57 | ✅ match |
| created via legacy path (order 144) | Open/1/162.0 | Open/1/162 | ✅ match |
| created via modern path (order 145) | Open/1/162.0 | Open/1/162 | ✅ match |
| totals order 1 | 239/11.95/11.35/22.65/261.05 | 239/11.95/11.35/22.65/261.05 | ✅ match |
| totals order 2 | 281/14.05/13.35/26.63/306.95 | 281/14.05/13.35/26.63/306.95 | ✅ match |
| totals order 3 | 41/0/2.05/4.09/47.15 | 41/0/2.05/4.09/47.15 | ✅ match |
| totals order 4 | 216/10.8/10.26/20.47/235.95 | 216/10.8/10.26/20.47/235.95 | ✅ match |
| totals order 5 | 232/11.6/11.02/21.98/253.4 | 232/11.6/11.02/21.98/253.4 | ✅ match |
| totals order 6 | 150/7.5/7.13/14.21/163.85 | 150/7.5/7.13/14.21/163.85 | ✅ match |
| totals order 7 | 130/0/6.5/12.97/149.45 | 130/0/6.5/12.97/149.45 | ✅ match |
| totals order 8 | 303/15.15/14.39/28.71/330.95 | 303/15.15/14.39/28.71/330.95 | ✅ match |
| totals order 144 | 162/8.1/7.7/15.35/176.95 | 162/8.1/7.7/15.35/176.95 | ✅ match |
| totals order 145 | 162/8.1/7.7/15.35/176.95 | 162/8.1/7.7/15.35/176.95 | ✅ match |
| guard 20002 pay-while-Open | 20002 | 20002 | ✅ match |
| guard 20003 cancel-without-reason | 20003 | 20003 | ✅ match |
| guard 20001 insufficient-stock | 20001 | 20001 | ✅ match |
| lifecycle Confirmed | Confirmed/162/176.95 | Confirmed/162/176.95 | ✅ match |
| guard 20004 line-freeze-after-Open | 20004 | 20004 | ✅ match |
| lifecycle Ready | Ready/162/176.95 | Ready/162/176.95 | ✅ match |
| lifecycle Paid | Paid/162/176.95 | Paid/162/176.95 | ✅ match |
| payment row written on Paid | 1/176.95 | 1/176.95 | ✅ match |

**Agreement: 31/31**
