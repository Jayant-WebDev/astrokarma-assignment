# Important implementation decisions

Brief notes on choices made for the wallet + per-minute consultation billing assignment.

---

## 1. App split: `wallet` vs `consultations`

**Decision:** Separate Django apps for money and sessions.

**Why:** Wallet recharge/idempotency is independent of the session state machine. Sessions depend on wallet helpers (`debit`, `has_minimum_to_start`) but wallet does not depend on sessions. Clear boundaries match the assignment domains and keep tests readable.

---

## 2. Roles via `Profile` + signal (not a custom User model)

**Decision:** Keep Django’s default `User`. Add `Profile` with `role` (`user` | `provider`). On user create, a signal creates a profile (default `user`).

**Why:** Avoids migrating to a custom user mid-assignment. Role checks stay simple (`request.user.profile.is_provider`). `AppConfig.ready()` imports signals so registration is reliable at startup.

---

## 3. Explicit transition map (`consultations/transitions.py`)

**Decision:** Central `ALLOWED_TRANSITIONS` dict; views call `assert_can_transition` and return HTTP 400 on failure.

**Why:** Assignment evaluates state management. One rule book is easier to reason about and test than scattered `if status == ...` checks. Invalid moves (e.g. end before start) are consistently rejected.

---

## 4. Input serializers vs read-only session serializer

**Decision:** Narrow input serializers for create / assign / bill; full `ConsultationSessionSerializer` is read-only for responses.

**Why:** Clients must not set `status`, `minutes_billed`, or `ended_by` directly. Lifecycle changes only go through dedicated action endpoints that enforce transitions and wallet rules.

---

## 5. Mock recharge idempotency keyed by `reference`

**Decision:** Each initiate creates a unique `reference`. Callback looks up by reference; if already `success`, return without crediting again.

**Why:** Matches “duplicate successful callback credits once.” `unique=True` on `reference` makes the payment attempt identity explicit.

---

## 6. Wallet debit helpers on the model

**Decision:** `Wallet.has_minimum_to_start`, `can_debit`, and `debit` (with `select_for_update` inside `atomic`).

**Why:** Start-session and billing share the same “never go negative” rules. Row locking reduces double-debit races if two bill requests overlap.

---

## 7. Billing uses target total minutes (`minutes_billed`)

**Decision:** `POST .../bill/` with `{"minutes": N}` means “ensure at least N minutes have been billed.” If `minutes_billed` already ≥ N, no extra charge.

**Why:** Satisfies duplicate-billing without a separate “billing ledger” table. Loop bills one minute at a time; if the next minute cannot be paid, mark session `completed`, `ended_by=system`, `end_reason=Insufficient Balance`, leave balance ≥ 0.

---

## 8. JWT + optional session auth

**Decision:** SimpleJWT as default API auth; `SessionAuthentication` kept for browsable API during development. Token URLs under `/api/auth/token/`.

**Why:** Assignment allows JWT or token auth. JWT is standard for API clients/tests; session login helps local exploration in the browser.

---

## 9. SQLite for local development

**Decision:** Default Django SQLite database.

**Why:** Assignment allows SQLite locally. No Postgres driver required to run or test. Switching to Postgres later is a settings/`DATABASES` change only.

---

## 10. Tests as API scenarios

**Decision:** Six DRF `APITestCase`s in `consultations/tests.py` hitting real URLs.

**Why:** Deliverable requires those scenarios. API tests verify wiring between auth, transitions, wallet, and billing—not only model methods in isolation.
