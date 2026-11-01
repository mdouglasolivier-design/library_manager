# Architecture

The addon is organized into models, controllers, security rules, data, views,
reports, static assets, and tests. Physical-book lending remains in the
backend. The eBook website uses public catalog routes and authenticated member
routes; borrower ownership comes from the signed-in user's partner record.

The backend Library Dashboard is an OWL client action. It reads metrics through
the current user's ORM access rights and combines physical-book and eBook loan
activity without elevated access.

eBook assets are stored as private database-backed binary fields. The reader
checks the current member's active loan before both rendering a reader page and
serving file bytes. Request/reservation status changes create in-portal
notifications and queue member email when an address is available. A daily
scheduled action queues one overdue reminder per active eBook loan per day.
